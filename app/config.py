from __future__ import annotations

import os
import pathlib
import platform
import socket
import subprocess
from typing import Optional, Sequence, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
STATIC_DIR = APP_DIR / "static"
TARGETS_FILE = APP_DIR / "targets.json"


def env(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(key, default)


def ping_once(ip: str) -> bool:
    if not ip:
        return False
    system = platform.system().lower()
    if "windows" in system:
        cmd = ["ping", "-n", "1", "-w", "1000", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
    try:
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def _parse_ports(raw: Optional[str]) -> Tuple[int, ...]:
    if not raw:
        return (3389, 445, 22)
    ports = []
    for chunk in raw.split(","):
        value = chunk.strip()
        if not value:
            continue
        try:
            port = int(value)
        except ValueError:
            continue
        if 1 <= port <= 65535 and port not in ports:
            ports.append(port)
    return tuple(ports) if ports else (3389, 445, 22)


def tcp_port_open(ip: str, port: int, timeout_sec: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def probe_online(ip: str, ports: Optional[Sequence[int]] = None, timeout_sec: float = 1.0) -> bool:
    if not ip:
        return False
    if ping_once(ip):
        return True

    effective_ports = tuple(ports) if ports is not None else _parse_ports(env("STATUS_TCP_PORTS"))
    for port in effective_ports:
        if tcp_port_open(ip, int(port), timeout_sec=timeout_sec):
            return True
    return False
