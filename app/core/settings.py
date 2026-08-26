from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import STATIC_DIR, env


def _env_int(key: str, default: int) -> int:
    raw = env(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    raw = env(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = env(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    lan_iface: str
    broadcast: str
    wol_method: str
    log_path: Path
    log_retention_days: int
    log_max_limit: int
    host: str
    port: int
    static_dir: Path
    boot_db_path: Path
    ubuntu_boot_enabled: bool
    ubuntu_boot_target: str
    windows_ssh_alias: str
    ubuntu_ssh_alias: str
    wol_ssh_config: Path
    windows_ready_timeout: int
    ubuntu_ready_timeout: int
    boot_job_timeout: int
    boot_poll_interval: float
    ssh_command_timeout: int
    reboot_start_timeout: int
    boot_job_retention_days: int


@lru_cache()
def get_settings() -> Settings:
    log_path = Path(env("LOG_PATH", "logs/wol-web.jsonl"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        lan_iface=env("LAN_IFACE", "eno1"),
        # A limited broadcast is a safe default across LAN renumbering. Operators
        # should still prefer the subnet-directed broadcast in .env.
        broadcast=env("BROADCAST", "255.255.255.255"),
        wol_method=env("WOL_METHOD", "python").lower(),
        log_path=log_path,
        log_retention_days=_env_int("LOG_RETENTION_DAYS", 7),
        log_max_limit=_env_int("LOG_MAX_LIMIT", 500),
        host=env("HOST", "127.0.0.1"),
        port=_env_int("PORT", 8000),
        static_dir=STATIC_DIR,
        boot_db_path=Path(env("BOOT_DB_PATH", "data/boot-jobs.sqlite3")),
        ubuntu_boot_enabled=_env_bool("UBUNTU_BOOT_ENABLED", False),
        ubuntu_boot_target=env("UBUNTU_BOOT_TARGET", "mainpc"),
        windows_ssh_alias=env("WINDOWS_SSH_ALIAS", "mainpc-windows"),
        ubuntu_ssh_alias=env("UBUNTU_SSH_ALIAS", "mainpc-ubuntu"),
        wol_ssh_config=Path(env("WOL_SSH_CONFIG", "/run/wol-ssh/config")),
        windows_ready_timeout=_env_int("WINDOWS_READY_TIMEOUT", 180),
        ubuntu_ready_timeout=_env_int("UBUNTU_READY_TIMEOUT", 300),
        boot_job_timeout=_env_int("BOOT_JOB_TIMEOUT", 480),
        boot_poll_interval=_env_float("BOOT_POLL_INTERVAL", 5.0),
        ssh_command_timeout=_env_int("SSH_COMMAND_TIMEOUT", 10),
        reboot_start_timeout=_env_int("REBOOT_START_TIMEOUT", 30),
        boot_job_retention_days=_env_int("BOOT_JOB_RETENTION_DAYS", 7),
    )
