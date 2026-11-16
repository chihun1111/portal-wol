import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.settings import get_settings
from app.services import logs


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    settings = replace(
        get_settings(), log_path=path, log_retention_days=0, log_max_limit=3,
    )
    monkeypatch.setattr(logs, "get_settings", lambda: settings)
    monkeypatch.setattr(logs, "_LAST_PRUNE_TS", 0.0)
    return path


def write_records(path, records):
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def test_logs_are_ordered_by_time_with_stable_ties_and_capped(log_path):
    write_records(log_path, [
        {"evt": "old", "ts": "2026-01-01T00:00:00Z"},
        {"evt": "first-tie", "ts": "2026-01-03T00:00:00+00:00"},
        {"evt": "second-tie", "ts": "2026-01-03T09:00:00+09:00"},
        {"evt": "newest", "ts": "2026-01-04T00:00:00"},
        {"evt": "middle", "ts": "2026-01-02T00:00:00.001Z"},
    ])

    assert [entry["evt"] for entry in logs.read_logs(2)] == ["newest", "first-tie"]
    for limit in (3, 100, 0, -1):
        assert [entry["evt"] for entry in logs.read_logs(limit)] == [
            "newest", "first-tie", "second-tie",
        ]


def test_corrupt_records_and_non_string_timestamps_do_not_break_reads(log_path, monkeypatch):
    settings = replace(logs.get_settings(), log_max_limit=20)
    monkeypatch.setattr(logs, "get_settings", lambda: settings)
    log_path.write_text(
        '\n{broken\n[]\nnull\n42\n"text"\n'
        '{"evt":"numeric", "ts":123}\n'
        '{"evt":"object", "ts":{}}\n'
        '{"evt":"invalid", "ts":"not-a-date"}\n'
        '{"evt":"non-finite", "ts":NaN}\n'
        '{"evt":"infinite", "value":Infinity}\n'
        '{"evt":"positive-overflow", "value":1e999}\n'
        '{"evt":"negative-overflow", "value":-1e999}\n'
        '{"evt":"missing"}\n'
        '{"evt":"good", "ts":"2026-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )

    assert [entry["evt"] for entry in logs.read_logs(20)] == [
        "good", "numeric", "object", "invalid", "missing",
    ]


def test_missing_log_returns_empty(log_path):
    assert logs.read_logs(20) == []


def test_prune_keeps_recent_and_unknown_dates_and_file_permissions(log_path):
    now = datetime.now(timezone.utc)
    write_records(log_path, [
        {"evt": "expired", "ts": (now - timedelta(days=10)).isoformat()},
        {"evt": "recent", "ts": now.isoformat()},
        {"evt": "unknown", "ts": 42},
        [],
        None,
    ])
    log_path.chmod(0o640)

    logs._prune_logs_locked(log_path, now - timedelta(days=7))

    assert [entry["evt"] for entry in logs.read_logs(20)] == ["recent", "unknown"]
    assert log_path.stat().st_mode & 0o777 == 0o640
    assert list(log_path.parent.glob("*.tmp")) == []


def test_failed_atomic_prune_preserves_original_and_retries(log_path, monkeypatch, caplog):
    original = '{"evt":"original", "ts":"2020-01-01T00:00:00Z"}\n'
    log_path.write_text(original, encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(logs.os, "replace", fail_replace)
    logs._maybe_prune_locked(1000, 7, log_path)

    assert log_path.read_text(encoding="utf-8") == original
    assert logs._LAST_PRUNE_TS == 0
    assert list(log_path.parent.glob("*.tmp")) == []
    assert "Unable to prune event log" in caplog.text


def test_append_failure_is_reported_without_failing_the_action(log_path, monkeypatch, caplog):
    original_open = Path.open

    def fail_append(path, mode="r", *args, **kwargs):
        if path == log_path and mode == "a":
            raise OSError("simulated full disk")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_append)
    logs.log_event({"evt": "wake", "target": "testpc"})

    assert "Unable to append event log" in caplog.text


def test_log_event_does_not_mutate_callers_event(log_path):
    event = {"evt": "wake", "target": "testpc"}
    logs.log_event(event)

    assert event == {"evt": "wake", "target": "testpc"}
    saved = logs.read_logs(1)[0]
    assert saved["evt"] == "wake"
    assert saved["target"] == "testpc"
    assert logs._parse_ts(saved["ts"]) is not None


def test_retention_failure_does_not_lose_the_new_event(log_path, monkeypatch):
    settings = replace(logs.get_settings(), log_retention_days=7)
    monkeypatch.setattr(logs, "get_settings", lambda: settings)

    def fail_replace(*_args):
        raise PermissionError("simulated retention permission failure")

    monkeypatch.setattr(logs.os, "replace", fail_replace)
    logs.log_event({"evt": "wake", "target": "testpc"})

    assert logs.read_logs(1)[0]["evt"] == "wake"


def test_large_log_keeps_only_the_latest_requested_entries(log_path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    write_records(log_path, [
        {"evt": f"event-{index}", "ts": (start + timedelta(seconds=index)).isoformat()}
        for index in range(5000)
    ])

    assert [entry["evt"] for entry in logs.read_logs(2)] == ["event-4999", "event-4998"]


def test_slow_read_does_not_block_append_or_include_later_events(log_path, monkeypatch):
    write_records(log_path, [{"evt": "original", "ts": "2020-01-01T00:00:00Z"}])
    reading = threading.Event()
    release = threading.Event()
    original_iter_records = logs._iter_records

    def paused_records(stream):
        reading.set()
        assert release.wait(3)
        yield from original_iter_records(stream)

    monkeypatch.setattr(logs, "_iter_records", paused_records)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(logs.read_logs, 3)
        try:
            assert reading.wait(3)
            writer = pool.submit(logs.log_event, {"evt": "appended"})
            writer.result(timeout=3)
        finally:
            release.set()
        assert [entry["evt"] for entry in reader.result(timeout=3)] == ["original"]

    assert [entry["evt"] for entry in logs.read_logs(3)] == ["appended", "original"]
