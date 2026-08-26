import sqlite3
import subprocess
import time
from dataclasses import replace

import pytest

from app.core.settings import get_settings
from app.services import boot_jobs
from app.services.boot_jobs import ActiveBootJobError, BootJobManager, BootJobNotCancellableError


def make_manager(tmp_path, **overrides):
    defaults = {
        "boot_db_path": tmp_path / "boot-jobs.sqlite3",
        "ubuntu_boot_enabled": True,
        "ubuntu_boot_target": "mainpc",
        "boot_poll_interval": 0.01,
        "windows_ready_timeout": 1,
        "ubuntu_ready_timeout": 1,
        "boot_job_timeout": 3,
        "ssh_command_timeout": 1,
        "reboot_start_timeout": 1,
    }
    defaults.update(overrides)
    manager = BootJobManager(replace(get_settings(), **defaults))
    manager._audit = lambda *_args, **_kwargs: None
    manager.startup()
    return manager


def wait_for_terminal(manager, job_id, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get_job(job_id)
        if job["terminal"]:
            return job
        time.sleep(0.01)
    raise AssertionError("boot job did not finish")


def test_already_running_ubuntu_succeeds_without_wake(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: True)
    monkeypatch.setattr(manager, "_probe_windows", lambda: pytest.fail("Windows probe should not run"))
    monkeypatch.setattr(boot_jobs, "wake_target", lambda *_args, **_kwargs: pytest.fail("WOL should not run"))

    job = manager.create_job("mainpc", "user@example.com")
    finished = wait_for_terminal(manager, job["id"])

    assert finished["state"] == "succeeded"
    assert finished["stage"] == "succeeded"
    assert set(finished) == {
        "id",
        "target",
        "state",
        "stage",
        "terminal",
        "can_cancel",
        "created_at",
        "updated_at",
        "error_code",
    }


def test_windows_flow_sets_bootnext_reboots_and_waits_for_ubuntu(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    state = {"rebooted": False}
    commands = []
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: state["rebooted"])
    monkeypatch.setattr(manager, "_probe_windows", lambda: not state["rebooted"])

    def windows_command(command):
        commands.append(command)
        if command == "reboot":
            state["rebooted"] = True
        return True

    monkeypatch.setattr(manager, "_windows_command", windows_command)

    job = manager.create_job("mainpc", "user@example.com")
    finished = wait_for_terminal(manager, job["id"])

    assert finished["state"] == "succeeded"
    assert commands == ["set-ubuntu-once", "reboot"]


def test_offline_flow_sends_wol_then_times_out_waiting_for_windows(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, windows_ready_timeout=1, boot_job_timeout=2)
    wake_calls = []
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: False)
    monkeypatch.setattr(manager, "_probe_windows", lambda: False)
    monkeypatch.setattr(boot_jobs, "wake_target", lambda target, audit: wake_calls.append((target, audit)))

    job = manager.create_job("mainpc", "user@example.com")
    finished = wait_for_terminal(manager, job["id"])

    assert wake_calls == [("mainpc", True)]
    assert finished["state"] == "timed_out"
    assert finished["error_code"] == "windows_not_ready"


def test_offline_flow_waits_for_windows_login_before_setting_bootnext(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    state = {"awake": False, "ubuntu": False}
    flow = []
    stages = []
    manager._audit = lambda _job, _target, _actor, stage, *_args: stages.append(stage)

    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: state["ubuntu"])

    def probe_windows():
        if state["awake"]:
            flow.append("windows_login_ready")
            return True
        return False

    def wake_target(target, audit):
        flow.append("wake")
        assert target == "mainpc"
        assert audit is True
        state["awake"] = True

    def windows_command(command):
        flow.append(command)
        if command == "reboot":
            state["ubuntu"] = True
        return True

    monkeypatch.setattr(manager, "_probe_windows", probe_windows)
    monkeypatch.setattr(manager, "_windows_command", windows_command)
    monkeypatch.setattr(boot_jobs, "wake_target", wake_target)

    job = manager.create_job("mainpc", "user@example.com")
    finished = wait_for_terminal(manager, job["id"])

    assert finished["state"] == "succeeded"
    assert flow == ["wake", "windows_login_ready", "set-ubuntu-once", "reboot"]
    assert stages.index("windows_login_ready") < stages.index("setting_bootnext")


def test_duplicate_job_is_rejected_and_early_job_can_be_cancelled(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)

    def slow_probe():
        time.sleep(0.2)
        return False

    monkeypatch.setattr(manager, "_probe_ubuntu", slow_probe)
    monkeypatch.setattr(manager, "_probe_windows", lambda: False)
    monkeypatch.setattr(boot_jobs, "wake_target", lambda *_args, **_kwargs: None)

    first = manager.create_job("mainpc", "user@example.com")
    with pytest.raises(ActiveBootJobError) as exc_info:
        manager.create_job("mainpc", "other@example.com")
    assert exc_info.value.job["id"] == first["id"]

    cancelled = manager.cancel_job(first["id"])
    assert cancelled["state"] == "cancelled"
    assert cancelled["terminal"] is True


def test_startup_marks_interrupted_jobs_failed(tmp_path):
    manager = make_manager(tmp_path)
    now = manager._now()
    with sqlite3.connect(manager.db_path) as conn:
        conn.execute(
            """
            INSERT INTO boot_jobs
                (id, target, actor, state, stage, terminal, can_cancel,
                 created_at, updated_at, error_code)
            VALUES ('interrupted', 'mainpc', 'user@example.com', 'running',
                    'waiting_for_windows', 0, 1, ?, ?, NULL)
            """,
            (now, now),
        )

    restarted = BootJobManager(manager.settings)
    restarted._audit = lambda *_args, **_kwargs: None
    restarted.startup()
    job = restarted.get_job("interrupted")

    assert job["state"] == "failed"
    assert job["error_code"] == "service_restarted"
    assert job["can_cancel"] is False


def test_ssh_requires_exact_success_token(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)

    monkeypatch.setattr(
        boot_jobs.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, stdout="WINDOWS_READY_V1\n", stderr=""),
    )
    assert manager._probe_windows() is True

    monkeypatch.setattr(
        boot_jobs.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, stdout="WINDOWS_READY_V1 extra", stderr=""),
    )
    assert manager._probe_windows() is False

    monkeypatch.setattr(
        boot_jobs.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 255, stdout="", stderr="host key mismatch"),
    )
    assert manager._probe_windows() is False


def test_bootnext_failure_stops_before_reboot(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    commands = []
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: False)
    monkeypatch.setattr(manager, "_probe_windows", lambda: True)

    def windows_command(command):
        commands.append(command)
        return False

    monkeypatch.setattr(manager, "_windows_command", windows_command)
    job = manager.create_job("mainpc", "user@example.com")
    finished = wait_for_terminal(manager, job["id"])

    assert finished["error_code"] == "bootnext_set_failed"
    assert commands == ["set-ubuntu-once"]


def test_reboot_failure_rolls_back_bootnext_when_windows_stays_up(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    commands = []
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: False)
    monkeypatch.setattr(manager, "_probe_windows", lambda: True)
    monkeypatch.setattr(manager, "_observe_ambiguous_reboot", lambda _deadline: "still_windows")

    def windows_command(command):
        commands.append(command)
        return command != "reboot"

    monkeypatch.setattr(manager, "_windows_command", windows_command)
    job = manager.create_job("mainpc", "user@example.com")
    finished = wait_for_terminal(manager, job["id"])

    assert finished["error_code"] == "reboot_not_started"
    assert commands == ["set-ubuntu-once", "reboot", "clear-ubuntu-once"]


def test_accepted_reboot_rolls_back_when_windows_never_goes_down(tmp_path, monkeypatch):
    manager = make_manager(
        tmp_path,
        reboot_start_timeout=1,
        boot_job_timeout=5,
        ubuntu_ready_timeout=4,
        boot_poll_interval=0.01,
    )
    commands = []
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: False)
    monkeypatch.setattr(manager, "_probe_windows", lambda: True)

    def windows_command(command):
        commands.append(command)
        return True

    monkeypatch.setattr(manager, "_windows_command", windows_command)
    job = manager.create_job("mainpc", "user@example.com")
    finished = wait_for_terminal(manager, job["id"], timeout=5)

    assert finished["error_code"] == "reboot_not_started"
    assert commands == ["set-ubuntu-once", "reboot", "clear-ubuntu-once"]


def test_job_cannot_be_cancelled_after_bootnext_stage(tmp_path):
    manager = make_manager(tmp_path)
    now = manager._now()
    with sqlite3.connect(manager.db_path) as conn:
        conn.execute(
            """
            INSERT INTO boot_jobs
                (id, target, actor, state, stage, terminal, can_cancel,
                 created_at, updated_at, error_code)
            VALUES ('locked', 'mainpc', 'user@example.com', 'running',
                    'setting_bootnext', 0, 0, ?, ?, NULL)
            """,
            (now, now),
        )
    with pytest.raises(BootJobNotCancellableError):
        manager.cancel_job("locked")


def test_boot_audit_contains_only_safe_fields(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    events = []
    manager._audit = BootJobManager._audit.__get__(manager, BootJobManager)
    monkeypatch.setattr(boot_jobs, "log_event", events.append)

    manager._audit("job-id", "mainpc", "user@example.com", "failed", "bootnext_set_failed")

    assert events == [
        {
            "evt": "boot-ubuntu",
            "job_id": "job-id",
            "target": "mainpc",
            "actor": "user@example.com",
            "stage": "failed",
            "error_code": "bootnext_set_failed",
        }
    ]


def test_feature_flag_and_target_are_enforced(tmp_path):
    disabled = make_manager(tmp_path, ubuntu_boot_enabled=False)
    with pytest.raises(Exception) as disabled_error:
        disabled.create_job("mainpc", "user@example.com")
    assert disabled_error.value.status_code == 503

    enabled = make_manager(tmp_path / "enabled")
    with pytest.raises(Exception) as target_error:
        enabled.create_job("otherpc", "user@example.com")
    assert target_error.value.status_code == 400
