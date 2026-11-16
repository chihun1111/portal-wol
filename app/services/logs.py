from __future__ import annotations

import heapq
import json
import logging
import math
import os
import stat
import tempfile
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterable, Iterator, List, Optional, Tuple

from ..core.settings import get_settings

_LOG = logging.getLogger(__name__)
_LOG_LOCK = threading.Lock()
_LAST_PRUNE_TS = 0.0
_UNKNOWN_TS = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _current_ts() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _invalid_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _finite_json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite JSON number: {value}")
    return number


def _iter_records(stream: Iterable[str]) -> Iterator[Tuple[Optional[datetime], Dict[str, Any]]]:
    for line in stream:
        if not line.strip():
            continue
        try:
            data = json.loads(
                line, parse_constant=_invalid_json_constant, parse_float=_finite_json_float,
            )
        except (ValueError, RecursionError):
            continue
        if not isinstance(data, dict):
            continue
        ts = _parse_ts(data.get("ts"))
        if ts is not None:
            try:
                data["ts"] = ts.astimezone().isoformat(timespec="seconds")
            except (ValueError, OverflowError):
                data["ts"] = ts.isoformat(timespec="seconds")
        yield ts, data


def _snapshot_lines(stream: BinaryIO, remaining: int) -> Iterator[str]:
    while remaining > 0:
        line = stream.readline(remaining)
        if not line:
            break
        remaining -= len(line)
        yield line.decode("utf-8", errors="replace")


def _prune_logs_locked(log_path: Path, cutoff: datetime) -> None:
    if not log_path.exists():
        return
    temporary_path: Optional[Path] = None
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as source:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=log_path.parent,
                prefix=f".{log_path.name}.", suffix=".tmp", delete=False,
            ) as output:
                temporary_path = Path(output.name)
                for ts, data in _iter_records(source):
                    if ts is None or ts >= cutoff:
                        output.write(json.dumps(data, ensure_ascii=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
                os.chmod(temporary_path, stat.S_IMODE(os.fstat(source.fileno()).st_mode))
        # An interrupted prune must leave the existing log intact. The temporary
        # file is on the same filesystem so replacement is atomic.
        os.replace(temporary_path, log_path)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                _LOG.exception("Unable to remove temporary event log")


def _maybe_prune_locked(now_epoch: float, retention_days: int, log_path: Path) -> None:
    global _LAST_PRUNE_TS
    if retention_days <= 0:
        return
    if _LAST_PRUNE_TS and now_epoch - _LAST_PRUNE_TS < 600:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        _prune_logs_locked(log_path, cutoff)
    except OSError:
        # Retention failure must not discard a successful append or prevent the
        # remaining log from being read. Retry on the next operation.
        _LOG.exception("Unable to prune event log")
    else:
        _LAST_PRUNE_TS = now_epoch


def log_event(evt: Dict[str, Any]) -> None:
    line = json.dumps({**evt, "ts": _current_ts()}, ensure_ascii=False)
    try:
        settings = get_settings()
        log_path = settings.log_path
        with _LOG_LOCK:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
            _maybe_prune_locked(time.time(), settings.log_retention_days, log_path)
    except OSError:
        # A disk failure after a power command must not report the command as
        # failed and encourage a duplicate request. Preserve diagnostics on stderr.
        _LOG.exception("Unable to append event log")


def read_logs(limit: int) -> List[Dict[str, Any]]:
    settings = get_settings()
    log_path = settings.log_path
    maximum = max(settings.log_max_limit, 1)
    limit = maximum if limit <= 0 else min(limit, maximum)
    with ExitStack() as stack:
        with _LOG_LOCK:
            _maybe_prune_locked(time.time(), settings.log_retention_days, log_path)
            try:
                stream = stack.enter_context(log_path.open("rb"))
            except FileNotFoundError:
                return []
            snapshot_size = os.fstat(stream.fileno()).st_size
        # Appends can continue while a bounded snapshot is parsed. Atomic pruning
        # leaves this open file intact, and later appends are excluded by size.
        # nlargest preserves the stable newest-first ordering, including ties.
        entries = heapq.nlargest(
            limit, _iter_records(_snapshot_lines(stream, snapshot_size)),
            key=lambda item: item[0] or _UNKNOWN_TS,
        )
    return [data for _ts, data in entries]
