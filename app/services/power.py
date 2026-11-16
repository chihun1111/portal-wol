from __future__ import annotations

import math
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import HTTPException

from ..core.settings import get_settings
from .logs import log_event
from .targets import (
    discover_mac_for_ip,
    get_target_or_404,
    record_wake,
    set_target_mac,
)

CommandType = Union[str, List[str], Dict[str, Any]]
DEFAULT_COMMAND_TIMEOUT_SEC = 15.0
_COMMAND_TEMPLATE_KEYS = ("name", "target", "ip", "mac")


def trim_text(value: str, limit: int = 4000) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)] + "..."


def _command_template_context(target: Dict[str, Any]) -> Dict[str, str]:
    name = str(target.get("name") or "")
    ip = str(target.get("ip") or "")
    mac = str(target.get("mac") or "")
    return {
        "name": name,
        "target": name,
        "ip": ip,
        "mac": mac,
    }


def _render_command_value(value: str, context: Dict[str, str]) -> str:
    rendered = value
    for key in _COMMAND_TEMPLATE_KEYS:
        placeholder = "{" + key + "}"
        if placeholder in rendered:
            token = context.get(key, "")
            if not token:
                raise ValueError(f"placeholder {placeholder} has no value")
            rendered = rendered.replace(placeholder, token)
    return rendered


def _render_command_with_target(
    cmd: Union[List[str], str], description: str, target: Dict[str, Any]
) -> Tuple[Union[List[str], str], str]:
    context = _command_template_context(target)
    if isinstance(cmd, list):
        rendered_cmd = [_render_command_value(item, context) for item in cmd]
    else:
        rendered_cmd = _render_command_value(cmd, context)
    rendered_description = _render_command_value(description, context)
    return rendered_cmd, rendered_description


def normalize_command_spec(spec: CommandType) -> Tuple[Union[List[str], str], bool, Optional[float], str]:
    shell = False
    timeout: Optional[float] = None
    description = ""
    if isinstance(spec, dict):
        cmd = spec.get("cmd") or spec.get("command")
        shell = bool(spec.get("shell", False))
        description = spec.get("desc") or spec.get("description") or ""
        timeout_value = spec.get("timeout")
        if timeout_value is not None:
            try:
                timeout = float(timeout_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("timeout must be a positive finite number") from exc
            if not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("timeout must be a positive finite number")
    elif isinstance(spec, list):
        cmd = spec
    else:
        cmd = spec
        shell = True
    if isinstance(cmd, list):
        cmd = [str(item) for item in cmd]
        if not cmd:
            raise ValueError("empty command list")
        if not description:
            description = " ".join(cmd)
    elif isinstance(cmd, str):
        cmd = cmd.strip()
        if not cmd:
            raise ValueError("empty command string")
        if not description:
            description = cmd
    else:
        raise ValueError("invalid command type")
    return cmd, shell, timeout, description


def send_magic_packet(
    mac: str,
    broadcast: str,
    packet_count: int = 1,
    packet_interval: float = 0.0,
) -> None:
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    packet = b"\xff" * 6 + mac_bytes * 16
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for index in range(max(packet_count, 1)):
            sock.sendto(packet, (broadcast, 9))
            if index + 1 < packet_count and packet_interval > 0:
                time.sleep(packet_interval)
    finally:
        sock.close()


def wake_target(name: str, audit: bool = True) -> Dict[str, Any]:
    settings = get_settings()
    target = get_target_or_404(name)
    name = target["name"]
    mac = target.get("mac")
    if not mac and target.get("ip"):
        discovered = discover_mac_for_ip(target["ip"])
        if discovered:
            updated = set_target_mac(
                name, discovered, expected_ip=target["ip"], only_if_missing=True,
            )
            mac = updated.get("mac")
            target = updated
    if not mac:
        raise HTTPException(400, detail={"error": "no mac for target", "target": name})
    packet_count = 1
    if settings.wol_method == "etherwake":
        try:
            rc = subprocess.call(
                ["/usr/sbin/etherwake", "-i", settings.lan_iface, mac],
                timeout=DEFAULT_COMMAND_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(504, detail="etherwake command timed out") from exc
        except OSError as exc:
            raise HTTPException(500, detail="etherwake command failed to start") from exc
        if rc != 0:
            raise HTTPException(500, "etherwake failed")
        method = "etherwake"
        destination = settings.lan_iface
    else:
        packet_count = settings.wol_packet_count
        send_magic_packet(
            mac,
            settings.broadcast,
            packet_count=packet_count,
            packet_interval=settings.wol_packet_interval,
        )
        method = "magic-packet"
        destination = settings.broadcast
    if audit:
        log_event({
            "evt": "wake",
            "target": name,
            "mac": mac,
            "from": "api",
            "method": method,
            "destination": destination,
            "packet_count": packet_count,
        })
    record_wake(name)
    return {
        "ok": True,
        "sent": method,
        "target": name,
        "destination": destination,
        "packet_count": packet_count,
    }


def _execute_current_os_command(name: str, action: str, settings: Any) -> Dict[str, Any]:
    timeout = max(settings.ssh_command_timeout, 1)

    def run_ssh(alias: str, command: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "ssh", "-F", str(settings.wol_ssh_config),
                "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "PreferredAuthentications=publickey",
                "-o", "IdentitiesOnly=yes", "-o", "NumberOfPasswordPrompts=0",
                alias, command,
            ],
            shell=False, timeout=timeout, check=False, capture_output=True, text=True,
        )

    detected_os = None
    alias = None
    probes = []
    for candidate_os, candidate_alias, probe, expected in (
        ("ubuntu", settings.ubuntu_ssh_alias, "uname -s", "Linux"),
        ("windows", settings.windows_ssh_alias, "probe-windows", "WINDOWS_READY_V1"),
    ):
        probe_audit = {"os": candidate_os, "alias": candidate_alias}
        try:
            result = run_ssh(candidate_alias, probe)
        except subprocess.TimeoutExpired:
            probes.append({**probe_audit, "error": "timeout", "timeout": timeout})
            continue
        except OSError as exc:
            probes.append({**probe_audit, "error": "oserror", "message": trim_text(str(exc))})
            continue
        probes.append({
            **probe_audit, "rc": result.returncode,
            "stdout": trim_text(result.stdout or ""),
            "stderr": trim_text(result.stderr or ""),
        })
        if result.returncode == 0 and (result.stdout or "").strip() == expected:
            detected_os, alias = candidate_os, candidate_alias
            break
    audit = {"evt": action, "target": name, "from": "api", "detected_os": detected_os}
    if alias is None:
        log_event({**audit, "error": "os_unavailable", "probes": probes})
        raise HTTPException(503, detail="current OS could not be verified over SSH")

    remote_command = "reboot-windows" if action == "reboot" else action
    if action == "reboot":
        audit["reboot_destination"] = "windows"
    description = f"ssh {alias} {remote_command}"
    audit["command"] = description
    try:
        result = run_ssh(alias, remote_command)
    except subprocess.TimeoutExpired as exc:
        log_event({**audit, "error": "timeout", "timeout": timeout})
        raise HTTPException(504, detail=f"{action} command timed out") from exc
    except OSError as exc:
        log_event({**audit, "error": "oserror", "message": str(exc)})
        raise HTTPException(500, detail=f"{action} command failed to start") from exc

    stdout, stderr = result.stdout or "", result.stderr or ""
    expected = {"shutdown": "SHUTDOWN_ACCEPTED_V1", "reboot": "REBOOT_ACCEPTED_V1"}[action]
    accepted = result.returncode == 0 and stdout.strip() == expected
    log_event({
        **audit, "rc": result.returncode, "stdout": trim_text(stdout),
        "stderr": trim_text(stderr), "accepted": accepted,
    })
    if not accepted:
        raise HTTPException(500, detail={
            "error": f"{action} command was not acknowledged",
            "detected_os": detected_os, "returncode": result.returncode,
            "stdout": trim_text(stdout, 1000), "stderr": trim_text(stderr, 1000),
        })
    response = {
        "ok": True, "action": action, "target": name, "detected_os": detected_os,
        "returncode": result.returncode, "stdout": stdout, "stderr": stderr,
        "command": description,
    }
    if action == "reboot":
        response["reboot_destination"] = "windows"
    return response


def execute_target_command(name: str, action: str) -> Dict[str, Any]:
    target = get_target_or_404(name)
    name = target["name"]
    settings = get_settings()
    if (settings.ubuntu_boot_enabled and name == settings.ubuntu_boot_target.strip().lower()
            and action in {"shutdown", "reboot"}):
        return _execute_current_os_command(name, action, settings)
    spec = target.get(action)
    if spec is None:
        raise HTTPException(400, f"no {action} command configured for target")
    try:
        cmd, use_shell, timeout, description = normalize_command_spec(spec)
    except ValueError as exc:
        raise HTTPException(400, detail=f"invalid {action} command: {exc}") from exc
    try:
        cmd, description = _render_command_with_target(cmd, description, target)
    except ValueError as exc:
        raise HTTPException(400, detail=f"invalid {action} command: {exc}") from exc
    effective_timeout = timeout if timeout is not None else DEFAULT_COMMAND_TIMEOUT_SEC
    try:
        result = subprocess.run(
            cmd,
            shell=use_shell,
            timeout=effective_timeout,
            check=False,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        log_event({
            "evt": action,
            "target": name,
            "from": "api",
            "command": description,
            "error": "timeout",
            "timeout": effective_timeout,
        })
        raise HTTPException(504, detail=f"{action} command timed out") from exc
    except OSError as exc:
        log_event({
            "evt": action,
            "target": name,
            "from": "api",
            "command": description,
            "error": "oserror",
            "message": str(exc),
        })
        raise HTTPException(500, detail=f"{action} command failed to start") from exc

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    log_payload = {
        "evt": action,
        "target": name,
        "from": "api",
        "command": description,
        "rc": result.returncode,
    }
    if stdout:
        log_payload["stdout"] = trim_text(stdout)
    if stderr:
        log_payload["stderr"] = trim_text(stderr)
    log_event(log_payload)

    if result.returncode != 0:
        raise HTTPException(
            500,
            detail={
                "error": f"{action} command failed",
                "returncode": result.returncode,
                "stdout": trim_text(stdout, 1000),
                "stderr": trim_text(stderr, 1000),
            },
        )
    return {
        "ok": True,
        "action": action,
        "target": name,
        "returncode": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "command": description,
    }
