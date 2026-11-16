import sqlite3
import subprocess
import time
from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.core.settings import get_settings
from app.services import boot_jobs, targets
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
            runner = manager._runners.get(job_id)
            if runner is not None:
                runner[0].join(timeout=max(deadline - time.monotonic(), 0))
                assert not runner[0].is_alive()
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
    runner = manager._runners[first["id"]][0]
    with pytest.raises(ActiveBootJobError) as exc_info:
        manager.create_job("mainpc", "other@example.com")
    assert exc_info.value.job["id"] == first["id"]

    cancelled = manager.cancel_job(first["id"])
    assert cancelled["state"] == "cancelled"
    assert cancelled["terminal"] is True
    runner.join(timeout=1)
    assert not runner.is_alive()


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


def test_cancellation_winning_bootnext_transition_prevents_power_commands(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    commands = []
    transition = manager._transition
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: False)
    monkeypatch.setattr(manager, "_probe_windows", lambda: True)
    monkeypatch.setattr(manager, "_windows_command", lambda command: commands.append(command) or True)
    # Run synchronously so all side effects have completed before asserting.
    monkeypatch.setattr(boot_jobs.threading.Thread, "start", lambda thread: thread.run())

    def cancel_before_transition(job_id, **kwargs):
        if kwargs["stage"] == "setting_bootnext":
            assert manager.cancel_job(job_id)["state"] == "cancelled"
        return transition(job_id, **kwargs)

    monkeypatch.setattr(manager, "_transition", cancel_before_transition)
    job = manager.create_job("mainpc", "user@example.com")

    assert manager.get_job(job["id"])["state"] == "cancelled"
    assert commands == []


def test_thread_start_failure_finishes_job_and_allows_retry(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)

    def fail_start(_thread):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(boot_jobs.threading.Thread, "start", fail_start)
    with pytest.raises(HTTPException) as exc_info:
        manager.create_job("mainpc", "user@example.com")
    assert exc_info.value.status_code == 503
    failed = manager.list_jobs()[0]
    assert failed["state"] == "failed"
    assert failed["error_code"] == "internal_error"
    assert manager._runners == {}

    monkeypatch.setattr(boot_jobs.threading.Thread, "start", lambda thread: thread.run())
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: True)
    retry = manager.create_job("mainpc", "user@example.com")
    assert manager.get_job(retry["id"])["state"] == "succeeded"


def test_database_connections_are_closed_after_reads_and_errors(tmp_path):
    manager = make_manager(tmp_path)
    with manager._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM boot_jobs").fetchone()[0] == 0
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")

    with pytest.raises(RuntimeError, match="abort transaction"):
        with manager._connect() as failed_conn:
            failed_conn.execute("CREATE TABLE IF NOT EXISTS rollback_check (value TEXT)")
            failed_conn.execute("INSERT INTO rollback_check VALUES ('uncommitted')")
            raise RuntimeError("abort transaction")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        failed_conn.execute("SELECT 1")
    with manager._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rollback_check").fetchone()[0] == 0


def test_power_actions_reserve_canonical_target_and_release_on_error(tmp_path):
    manager = make_manager(tmp_path)
    with pytest.raises(RuntimeError, match="command failed"):
        with manager.power_action(" MAINPC ") as target:
            assert target == "mainpc"
            with pytest.raises(HTTPException) as duplicate:
                with manager.power_action("mainpc"):
                    pytest.fail("a duplicate action must not run")
            assert duplicate.value.status_code == 409
            assert duplicate.value.detail["error"] == "target_busy"
            with pytest.raises(HTTPException) as boot_conflict:
                manager.create_job("MAINPC", "user@example.com")
            assert boot_conflict.value.status_code == 409
            assert boot_conflict.value.detail["error"] == "target_busy"
            raise RuntimeError("command failed")

    with manager.power_action("mainpc") as target:
        assert target == "mainpc"


def test_boot_reserves_target_until_cancelled_runner_finishes(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    monkeypatch.setattr(boot_jobs.threading.Thread, "start", lambda _thread: None)
    first = manager.create_job("mainpc", "user@example.com")
    runner = manager._runners[first["id"]][0]

    with pytest.raises(HTTPException) as active:
        with manager.power_action("MAINPC"):
            pytest.fail("power action must not interrupt a boot job")
    assert active.value.status_code == 409
    assert active.value.detail["error"] == "active_boot_job"
    assert active.value.detail["job"]["id"] == first["id"]

    manager.cancel_job(first["id"])
    with pytest.raises(HTTPException) as finishing:
        with manager.power_action("mainpc"):
            pytest.fail("cancelled runner has not exited yet")
    assert finishing.value.detail["error"] == "target_busy"
    with pytest.raises(HTTPException) as retry:
        manager.create_job("mainpc", "user@example.com")
    assert retry.value.detail["error"] == "target_busy"

    # A cancelled queued runner exits without any SSH or WOL operation.
    monkeypatch.setattr(manager, "_probe_ubuntu", lambda: pytest.fail("cancelled job must not probe"))
    runner.run()
    with manager.power_action("mainpc"):
        pass


def test_failed_boot_runner_releases_target(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    monkeypatch.setattr(boot_jobs.threading.Thread, "start", lambda thread: thread.run())

    def fail_probe():
        raise RuntimeError("unexpected probe failure")

    monkeypatch.setattr(manager, "_probe_ubuntu", fail_probe)
    job = manager.create_job("mainpc", "user@example.com")
    assert manager.get_job(job["id"])["error_code"] == "internal_error"
    with manager.power_action("mainpc"):
        pass


@pytest.mark.parametrize("mutation", ["delete", "rename"])
@pytest.mark.parametrize("operation", ["boot", "power"])
def test_target_is_resolved_after_a_concurrent_edit_finishes(tmp_path, monkeypatch, mutation, operation):
    manager = make_manager(tmp_path)
    original_lock = manager._lock

    class EditBeforeAcquire:
        """Complete another guarded request just before the next lock entry."""

        pending_edit = True

        def __enter__(self):
            if self.pending_edit:
                self.pending_edit = False
                with manager.power_action("mainpc") as target:
                    if mutation == "delete":
                        targets.delete_target(target)
                    else:
                        targets.update_target(target, {"name": "renamed-pc"})
            original_lock.acquire()
            return self

        def __exit__(self, *_args):
            original_lock.release()

    monkeypatch.setattr(manager, "_lock", EditBeforeAcquire())
    monkeypatch.setattr(boot_jobs.threading.Thread, "start", lambda _thread: None)
    with pytest.raises(HTTPException) as exc_info:
        if operation == "boot":
            manager.create_job("mainpc", "user@example.com")
        else:
            with manager.power_action("mainpc"):
                pytest.fail("a removed target must not be reserved")

    assert exc_info.value.status_code == 404
    assert manager.list_jobs() == []
