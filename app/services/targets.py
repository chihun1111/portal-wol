from __future__ import annotations

import ipaddress
import json
import platform
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from ..config import TARGETS_FILE
from .logs import log_event

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

_TARGETS_LOCK = threading.Lock()
_RUNTIME_STATE: Dict[str, Dict[str, Any]] = {}


def _now_ts() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_name(name: str) -> str:
    candidate = name.strip().lower()
    if not candidate:
        raise HTTPException(400, detail="name is required")
    if not NAME_PATTERN.fullmatch(candidate):
        raise HTTPException(400, detail="name must be 2-32 chars, lowercase letters, numbers, hyphen")
    return candidate


def _validate_ip(ip: str) -> str:
    value = ip.strip()
    if not value:
        raise HTTPException(400, detail="ip is required")
    try:
        addr = ipaddress.ip_address(value)
    except ValueError as exc:
        raise HTTPException(400, detail="invalid ip address") from exc
    if addr.version != 4:
        raise HTTPException(400, detail="ipv4 address required")
    return value


def _normalize_mac(mac: Optional[str]) -> Optional[str]:
    if not mac:
        return None
    value = mac.strip()
    if not value:
        return None
    value = value.replace("-", ":").upper()
    if not MAC_PATTERN.fullmatch(value):
        raise HTTPException(400, detail="invalid mac address; use AA:BB:CC:DD:EE:FF")
    return value


def _ensure_file() -> None:
    TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TARGETS_FILE.exists():
        state = {"targets": []}
        TARGETS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_loaded_target(target: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(target, dict):
        return None
    raw_name = str(target.get("name", "")).strip()
    raw_ip = str(target.get("ip", "")).strip()
    if not raw_name or not raw_ip:
        return None
    try:
        name = _normalize_name(raw_name)
        ip = _validate_ip(raw_ip)
    except HTTPException:
        return None
    mac = target.get("mac")
    try:
        normalized_mac = _normalize_mac(mac)
    except HTTPException:
        normalized_mac = None
    sanitized: Dict[str, Any] = dict(target)
    sanitized["name"] = name
    sanitized["ip"] = ip
    if normalized_mac is not None:
        sanitized["mac"] = normalized_mac
    else:
        sanitized.pop("mac", None)
    ts = _now_ts()
    sanitized.setdefault("created_at", ts)
    sanitized.setdefault("updated_at", ts)
    return sanitized


def _normalize_state(data: Any) -> Tuple[Dict[str, Any], bool]:
    targets: List[Dict[str, Any]] = []
    changed = False
    if isinstance(data, dict) and "targets" in data and isinstance(data["targets"], list):
        for item in data["targets"]:
            normalized = _normalize_loaded_target(item)
            if normalized is None:
                changed = True
                continue
            if normalized != item:
                changed = True
            targets.append(normalized)
    elif isinstance(data, dict):
        changed = True
        for name, item in data.items():
            if isinstance(item, dict):
                candidate = dict(item)
                candidate.setdefault("name", name)
                normalized = _normalize_loaded_target(candidate)
                if normalized is not None:
                    targets.append(normalized)
    elif isinstance(data, list):
        changed = True
        for item in data:
            normalized = _normalize_loaded_target(item)
            if normalized is not None:
                targets.append(normalized)
    else:
        changed = True
    unique: Dict[str, Dict[str, Any]] = {}
    for item in targets:
        unique[item["name"]] = item
    ordered = list(sorted(unique.values(), key=lambda t: t["name"]))
    return {"targets": ordered}, changed


def _load_state_locked() -> Dict[str, Any]:
    _ensure_file()
    text = TARGETS_FILE.read_text(encoding="utf-8")
    if not text.strip():
        state = {"targets": []}
        _save_state_locked(state)
        return state
    try:
        raw = json.loads(text)
    except Exception:
        state = {"targets": []}
        _save_state_locked(state)
        return state
    state, changed = _normalize_state(raw)
    if changed:
        _save_state_locked(state)
    return state


def _save_state_locked(state: Dict[str, Any]) -> None:
    serialized = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    temp_path = TARGETS_FILE.with_name(TARGETS_FILE.name + ".tmp")
    Path(temp_path).write_text(serialized, encoding="utf-8")
    Path(temp_path).replace(TARGETS_FILE)


def _find_index(targets: List[Dict[str, Any]], name: str) -> int:
    for idx, target in enumerate(targets):
        if target.get("name") == name:
            return idx
    return -1


def _update_runtime(name: str, **fields: Any) -> None:
    entry = _RUNTIME_STATE.setdefault(name, {})
    entry.update(fields)


def list_targets() -> List[Dict[str, Any]]:
    with _TARGETS_LOCK:
        state = _load_state_locked()
        results = []
        for target in state["targets"]:
            info = {
                "name": target.get("name"),
                "ip": target.get("ip"),
                "mac": target.get("mac"),
                "created_at": target.get("created_at"),
                "updated_at": target.get("updated_at"),
            }
            runtime = _RUNTIME_STATE.get(target["name"])
            if runtime:
                info.update(runtime)
            info["has_mac"] = bool(target.get("mac"))
            results.append(info)
        return results


def get_target(name: str) -> Optional[Dict[str, Any]]:
    normalized = _normalize_name(name)
    with _TARGETS_LOCK:
        state = _load_state_locked()
        for target in state["targets"]:
            if target.get("name") == normalized:
                return dict(target)
    return None


def get_target_or_404(name: str) -> Dict[str, Any]:
    target = get_target(name)
    if not target:
        raise HTTPException(404, detail="unknown target")
    return target


def create_target(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = _normalize_name(str(payload.get("name", "")))
    ip = _validate_ip(str(payload.get("ip", "")))
    mac = _normalize_mac(payload.get("mac"))
    ts = _now_ts()
    with _TARGETS_LOCK:
        state = _load_state_locked()
        if any(item.get("name") == name for item in state["targets"]):
            raise HTTPException(409, detail="duplicate target name")
        new_target: Dict[str, Any] = {
            "name": name,
            "ip": ip,
            "created_at": ts,
            "updated_at": ts,
        }
        if mac:
            new_target["mac"] = mac
        state["targets"].append(new_target)
        state["targets"] = list(sorted(state["targets"], key=lambda t: t["name"]))
        _save_state_locked(state)
    log_event({"evt": "target-create", "target": name, "ip": ip, "mac": mac})
    return new_target


def update_target(original_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized_original = _normalize_name(original_name)
    new_name = payload.get("name")
    ip = payload.get("ip")
    mac = payload.get("mac") if "mac" in payload else None

    with _TARGETS_LOCK:
        state = _load_state_locked()
        index = _find_index(state["targets"], normalized_original)
        if index == -1:
            raise HTTPException(404, detail="unknown target")
        target = dict(state["targets"][index])

        if new_name is not None:
            normalized_new = _normalize_name(str(new_name))
            if normalized_new != normalized_original and any(
                item.get("name") == normalized_new for item in state["targets"]
            ):
                raise HTTPException(409, detail="duplicate target name")
            target["name"] = normalized_new
        else:
            normalized_new = normalized_original

        if ip is not None:
            target["ip"] = _validate_ip(str(ip))

        if mac is not None:
            normalized_mac = _normalize_mac(mac)
            if normalized_mac:
                target["mac"] = normalized_mac
            else:
                target.pop("mac", None)

        target["updated_at"] = _now_ts()

        state["targets"][index] = target
        state["targets"] = list(sorted(state["targets"], key=lambda t: t["name"]))
        _save_state_locked(state)

        if normalized_original != normalized_new:
            if normalized_original in _RUNTIME_STATE:
                _RUNTIME_STATE[normalized_new] = _RUNTIME_STATE.pop(normalized_original)
    log_event({"evt": "target-update", "target": normalized_original, "updated": target.get("name")})
    return target


def delete_target(name: str) -> None:
    normalized = _normalize_name(name)
    with _TARGETS_LOCK:
        state = _load_state_locked()
        index = _find_index(state["targets"], normalized)
        if index == -1:
            raise HTTPException(404, detail="unknown target")
        removed = state["targets"].pop(index)
        _save_state_locked(state)
        _RUNTIME_STATE.pop(normalized, None)
    log_event({"evt": "target-delete", "target": normalized, "ip": removed.get("ip")})


def set_target_mac(name: str, mac: str) -> Dict[str, Any]:
    normalized_mac = _normalize_mac(mac)
    normalized_name = _normalize_name(name)
    with _TARGETS_LOCK:
        state = _load_state_locked()
        index = _find_index(state["targets"], normalized_name)
        if index == -1:
            raise HTTPException(404, detail="unknown target")
        target = dict(state["targets"][index])
        if target.get("mac") == normalized_mac:
            return target
        target["mac"] = normalized_mac
        target["updated_at"] = _now_ts()
        state["targets"][index] = target
        _save_state_locked(state)
    log_event({"evt": "target-mac-set", "target": normalized_name, "mac": normalized_mac})
    return target


def discover_mac_for_ip(ip: str) -> Optional[str]:
    system = platform.system().lower()
    commands: List[List[str]] = []
    if "windows" in system:
        commands.append(["arp", "-a", ip])
    else:
        commands.append(["ip", "neigh", "show", ip])
        commands.append(["arp", "-n", ip])
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=3)
        except Exception:
            continue
        output = f"{result.stdout}\n{result.stderr}".replace("-", ":").strip()
        match = MAC_PATTERN.search(output)
        if match:
            return match.group(0).upper()
    return None


def record_status(name: str, online: bool, ip: Optional[str] = None) -> None:
    _update_runtime(name, last_status_at=_now_ts(), online=online)
    if online and ip:
        try:
            mac = discover_mac_for_ip(ip)
            if mac:
                set_target_mac(name, mac)
        except HTTPException:
            pass


def record_wake(name: str) -> None:
    _update_runtime(name, last_wake_at=_now_ts())
