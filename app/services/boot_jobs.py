from __future__ import annotations

import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from ..core.settings import Settings, get_settings
from .logs import log_event
from .power import wake_target
from .targets import get_target_or_404

ACTIVE_STATES = ("queued", "running")
CANCELLABLE_STAGES = (
    "queued",
    "detecting_os",
    "waking",
    "waiting_for_windows",
    "windows_login_ready",
)
TERMINAL_STATES = ("succeeded", "failed", "timed_out", "cancelled")

WINDOWS_COMMAND_TOKENS = {
    "probe-windows": "WINDOWS_READY_V1",
    "set-ubuntu-once": "BOOTNEXT_SET_V1",
    "clear-ubuntu-once": "BOOTNEXT_CLEARED_V1",
    "reboot": "REBOOT_ACCEPTED_V1",
}


class ActiveBootJobError(Exception):
    def __init__(self, job: Dict[str, Any]):
        super().__init__("an active boot job already exists")
        self.job = job


class BootJobNotCancellableError(Exception):
    pass


class BootJobManager:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.db_path = Path(self.settings.boot_db_path)
        self._lock = threading.RLock()
        self._runners: Dict[str, tuple[threading.Thread, threading.Event]] = {}
        self._started = False

    def startup(self) -> None:
        with self._lock:
            if self._started:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS boot_jobs (
                        id TEXT PRIMARY KEY,
                        target TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        state TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        terminal INTEGER NOT NULL DEFAULT 0,
                        can_cancel INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        error_code TEXT
                    )
                    """
                )
                now = self._now()
                interrupted = conn.execute(
                    "SELECT id, target, actor FROM boot_jobs WHERE terminal = 0"
                ).fetchall()
                conn.execute(
                    """
                    UPDATE boot_jobs
                    SET state = 'failed', stage = 'failed', terminal = 1,
                        can_cancel = 0, updated_at = ?, error_code = 'service_restarted'
                    WHERE terminal = 0
                    """,
                    (now,),
                )
                cutoff = (
                    datetime.now(timezone.utc)
                    - timedelta(days=max(self.settings.boot_job_retention_days, 0))
                ).isoformat(timespec="seconds")
                if self.settings.boot_job_retention_days > 0:
                    conn.execute(
                        "DELETE FROM boot_jobs WHERE terminal = 1 AND updated_at < ?",
                        (cutoff,),
                    )
            self._started = True
        for row in interrupted:
            self._audit(row["id"], row["target"], row["actor"], "failed", "service_restarted")

    def shutdown(self) -> None:
        # Running jobs are deliberately not converted to user cancellations here.
        # A real process restart stops daemon threads; startup then records them as
        # failed/service_restarted from the persisted non-terminal rows.
        return

    def create_job(self, target: str, actor: str) -> Dict[str, Any]:
        self._ensure_started()
        if not self.settings.ubuntu_boot_enabled:
            raise HTTPException(503, detail={"error": "ubuntu_boot_disabled"})
        if target != self.settings.ubuntu_boot_target:
            raise HTTPException(400, detail={"error": "unsupported_boot_target"})
        get_target_or_404(target)

        with self._lock:
            active = self._get_active_locked(target)
            if active is not None:
                raise ActiveBootJobError(active)
            job_id = str(uuid.uuid4())
            now = self._now()
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO boot_jobs
                        (id, target, actor, state, stage, terminal, can_cancel,
                         created_at, updated_at, error_code)
                    VALUES (?, ?, ?, 'queued', 'queued', 0, 1, ?, ?, NULL)
                    """,
                    (job_id, target, actor, now, now),
                )
            cancel_event = threading.Event()
            thread = threading.Thread(
                target=self._run_job,
                args=(job_id, target, actor, cancel_event),
                name=f"boot-job-{job_id[:8]}",
                daemon=True,
            )
            self._runners[job_id] = (thread, cancel_event)
            job = self.get_job(job_id)
            self._audit(job_id, target, actor, "queued")
            thread.start()
        return job

    def get_job(self, job_id: str) -> Dict[str, Any]:
        self._ensure_started()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM boot_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, detail={"error": "unknown_job"})
        return self._public_job(row)

    def list_jobs(self, target: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        self._ensure_started()
        effective_limit = max(1, min(limit, 100))
        with self._connect() as conn:
            if target:
                rows = conn.execute(
                    """
                    SELECT * FROM boot_jobs WHERE target = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (target, effective_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM boot_jobs ORDER BY created_at DESC LIMIT ?",
                    (effective_limit,),
                ).fetchall()
        return [self._public_job(row) for row in rows]

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        self._ensure_started()
        with self._lock:
            job = self.get_job(job_id)
            if job["terminal"]:
                return job
            if not job["can_cancel"] or job["stage"] not in CANCELLABLE_STAGES:
                raise BootJobNotCancellableError()
            runner = self._runners.get(job_id)
            if runner is not None:
                runner[1].set()
            self._transition(
                job_id,
                state="cancelled",
                stage="cancelled",
                terminal=True,
                can_cancel=False,
                error_code=None,
            )
            return self.get_job(job_id)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_started(self) -> None:
        if not self._started:
            self.startup()

    def _get_active_locked(self, target: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM boot_jobs
                WHERE target = ? AND terminal = 0
                ORDER BY created_at DESC LIMIT 1
                """,
                (target,),
            ).fetchone()
        return self._public_job(row) if row is not None else None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _public_job(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "target": row["target"],
            "state": row["state"],
            "stage": row["stage"],
            "terminal": bool(row["terminal"]),
            "can_cancel": bool(row["can_cancel"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "error_code": row["error_code"],
        }

    def _transition(
        self,
        job_id: str,
        *,
        state: str,
        stage: str,
        terminal: bool = False,
        can_cancel: bool = False,
        error_code: Optional[str] = None,
    ) -> bool:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT target, actor, terminal FROM boot_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                if row is None or row["terminal"]:
                    return False
                conn.execute(
                    """
                    UPDATE boot_jobs
                    SET state = ?, stage = ?, terminal = ?, can_cancel = ?,
                        updated_at = ?, error_code = ?
                    WHERE id = ?
                    """,
                    (
                        state,
                        stage,
                        int(terminal),
                        int(can_cancel),
                        self._now(),
                        error_code,
                        job_id,
                    ),
                )
        self._audit(job_id, row["target"], row["actor"], stage, error_code)
        return True

    def _audit(
        self,
        job_id: str,
        target: str,
        actor: str,
        stage: str,
        error_code: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "evt": "boot-ubuntu",
            "job_id": job_id,
            "target": target,
            "actor": actor,
            "stage": stage,
        }
        if error_code:
            payload["error_code"] = error_code
        log_event(payload)

    def _run_job(
        self,
        job_id: str,
        target: str,
        actor: str,
        cancel_event: threading.Event,
    ) -> None:
        deadline = time.monotonic() + max(self.settings.boot_job_timeout, 1)
        try:
            self._transition(
                job_id,
                state="running",
                stage="detecting_os",
                can_cancel=True,
            )
            if self._is_cancelled(job_id, cancel_event):
                return
            if self._probe_ubuntu():
                self._succeed(job_id)
                return

            windows_ready = self._probe_windows()
            if not windows_ready:
                self._transition(
                    job_id,
                    state="running",
                    stage="waking",
                    can_cancel=True,
                )
                if self._is_cancelled(job_id, cancel_event):
                    return
                try:
                    # Keep the actual WOL destination in the audit log. This makes
                    # an offline Ubuntu boot job independently diagnosable.
                    wake_target(target, audit=True)
                except Exception:
                    self._fail(job_id, "wake_failed")
                    return
                self._transition(
                    job_id,
                    state="running",
                    stage="waiting_for_windows",
                    can_cancel=True,
                )
                phase_deadline = min(
                    deadline,
                    time.monotonic() + max(self.settings.windows_ready_timeout, 1),
                )
                while time.monotonic() < phase_deadline:
                    if self._is_cancelled(job_id, cancel_event):
                        return
                    if self._probe_ubuntu():
                        self._succeed(job_id)
                        return
                    if self._probe_windows():
                        windows_ready = True
                        break
                    cancel_event.wait(max(self.settings.boot_poll_interval, 0.1))
                if not windows_ready:
                    self._timeout(job_id, "windows_not_ready")
                    return

            # _probe_windows performs a real key-only SSH login and requires the
            # restricted Windows wrapper's exact readiness token. Do not set
            # BootNext until that authenticated login has completed.
            self._transition(
                job_id,
                state="running",
                stage="windows_login_ready",
                can_cancel=True,
            )

            if time.monotonic() >= deadline:
                self._timeout(job_id, "job_timeout")
                return
            if self._is_cancelled(job_id, cancel_event):
                return

            self._transition(
                job_id,
                state="running",
                stage="setting_bootnext",
                can_cancel=False,
            )
            if not self._windows_command("set-ubuntu-once"):
                self._fail(job_id, "bootnext_set_failed")
                return

            self._transition(
                job_id,
                state="running",
                stage="rebooting",
                can_cancel=False,
            )
            reboot_accepted = self._windows_command("reboot")
            saw_windows_down = False
            if not reboot_accepted:
                observation = self._observe_ambiguous_reboot(deadline)
                if observation == "ubuntu":
                    self._succeed(job_id)
                    return
                if observation == "still_windows":
                    rollback_ok = self._windows_command("clear-ubuntu-once")
                    self._fail(
                        job_id,
                        "reboot_not_started" if rollback_ok else "rollback_failed",
                    )
                    return
                saw_windows_down = observation == "down"

            self._transition(
                job_id,
                state="running",
                stage="waiting_for_ubuntu",
                can_cancel=False,
            )
            ubuntu_deadline = min(
                deadline,
                time.monotonic() + max(self.settings.ubuntu_ready_timeout, 1),
            )
            windows_seen = 0
            reboot_started_at = time.monotonic()
            while time.monotonic() < ubuntu_deadline:
                if self._probe_ubuntu():
                    self._succeed(job_id)
                    return
                windows_is_ready = self._probe_windows()
                if not windows_is_ready:
                    saw_windows_down = True
                    windows_seen = 0
                elif time.monotonic() - reboot_started_at >= max(
                    self.settings.reboot_start_timeout, 1
                ):
                    windows_seen += 1
                    if windows_seen >= 3:
                        if saw_windows_down:
                            self._fail(job_id, "ubuntu_boot_failed")
                        else:
                            rollback_ok = self._windows_command("clear-ubuntu-once")
                            self._fail(
                                job_id,
                                "reboot_not_started" if rollback_ok else "rollback_failed",
                            )
                        return
                time.sleep(max(self.settings.boot_poll_interval, 0.1))
            self._timeout(job_id, "ubuntu_not_ready")
        except Exception:
            self._fail(job_id, "internal_error")
        finally:
            with self._lock:
                self._runners.pop(job_id, None)

    def _is_cancelled(self, job_id: str, cancel_event: threading.Event) -> bool:
        if not cancel_event.is_set():
            return False
        job = self.get_job(job_id)
        if not job["terminal"]:
            self._transition(
                job_id,
                state="cancelled",
                stage="cancelled",
                terminal=True,
                can_cancel=False,
            )
        return True

    def _run_ssh(self, alias: str, remote_command: str, expected: str) -> bool:
        command = [
            "ssh",
            "-F",
            str(self.settings.wol_ssh_config),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "NumberOfPasswordPrompts=0",
            alias,
            remote_command,
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=max(self.settings.ssh_command_timeout, 1),
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and result.stdout.strip() == expected

    def _probe_windows(self) -> bool:
        return self._windows_command("probe-windows")

    def _probe_ubuntu(self) -> bool:
        return self._run_ssh(
            self.settings.ubuntu_ssh_alias,
            "uname -s",
            "Linux",
        )

    def _windows_command(self, command: str) -> bool:
        return self._run_ssh(
            self.settings.windows_ssh_alias,
            command,
            WINDOWS_COMMAND_TOKENS[command],
        )

    def _observe_ambiguous_reboot(self, deadline: float) -> str:
        observation_deadline = min(
            deadline,
            time.monotonic() + max(self.settings.reboot_start_timeout, 1),
        )
        while time.monotonic() < observation_deadline:
            if self._probe_ubuntu():
                return "ubuntu"
            if not self._probe_windows():
                return "down"
            time.sleep(max(self.settings.boot_poll_interval, 0.1))
        return "still_windows"

    def _succeed(self, job_id: str) -> None:
        self._transition(
            job_id,
            state="succeeded",
            stage="succeeded",
            terminal=True,
            can_cancel=False,
        )

    def _fail(self, job_id: str, error_code: str) -> None:
        self._transition(
            job_id,
            state="failed",
            stage="failed",
            terminal=True,
            can_cancel=False,
            error_code=error_code,
        )

    def _timeout(self, job_id: str, error_code: str) -> None:
        self._transition(
            job_id,
            state="timed_out",
            stage="timed_out",
            terminal=True,
            can_cancel=False,
            error_code=error_code,
        )
