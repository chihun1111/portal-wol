import subprocess
from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.core.settings import get_settings
from app.services import power


@pytest.fixture
def setup_power(monkeypatch):
    settings = replace(get_settings(), ubuntu_boot_enabled=True,
                       ubuntu_boot_target="mainpc", ssh_command_timeout=2)
    events = []
    monkeypatch.setattr(power, "get_settings", lambda: settings)
    monkeypatch.setattr(power, "get_target_or_404", lambda name: {
        "name": name, "shutdown": ["legacy-shutdown"], "reboot": ["legacy-reboot"],
    })
    monkeypatch.setattr(power, "log_event", events.append)
    return settings, events


def completed(stdout="", rc=0):
    return subprocess.CompletedProcess([], rc, stdout=stdout, stderr="")


@pytest.mark.parametrize("os_name", ["ubuntu", "windows"])
@pytest.mark.parametrize("action,token", [
    ("shutdown", "SHUTDOWN_ACCEPTED_V1"), ("reboot", "REBOOT_ACCEPTED_V1"),
])
def test_current_os_routes_to_verified_alias(setup_power, monkeypatch, os_name, action, token):
    settings, events = setup_power
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 2
        assert "StrictHostKeyChecking=yes" in cmd
        assert "PreferredAuthentications=publickey" in cmd
        assert "IdentitiesOnly=yes" in cmd
        if cmd[-1] == "uname -s":
            return completed("Linux\n" if os_name == "ubuntu" else "", 0 if os_name == "ubuntu" else 255)
        if cmd[-1] == "probe-windows":
            return completed("WINDOWS_READY_V1\n")
        return completed(token + "\n")

    monkeypatch.setattr(power.subprocess, "run", run)
    result = power.execute_target_command("mainpc", action)
    alias = settings.ubuntu_ssh_alias if os_name == "ubuntu" else settings.windows_ssh_alias
    assert result["detected_os"] == os_name
    remote_command = "reboot-windows" if action == "reboot" else action
    assert calls[-1][-2:] == [alias, remote_command]
    if action == "reboot":
        assert result["reboot_destination"] == "windows"
        assert events[-1]["reboot_destination"] == "windows"
    else:
        assert "reboot_destination" not in result
    assert events[-1]["detected_os"] == os_name
    assert events[-1]["accepted"] is True


@pytest.mark.parametrize("failure", ["wrong-token", "nonzero", "timeout", "oserror"])
def test_unavailable_os_never_executes_power(setup_power, monkeypatch, failure):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd[-1])
        if failure == "timeout":
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
        if failure == "oserror":
            raise OSError("ssh missing")
        return completed("Linux extra" if cmd[-1] == "uname -s" else "WINDOWS_READY_V1 extra",
                         255 if failure == "nonzero" else 0)

    monkeypatch.setattr(power.subprocess, "run", run)
    with pytest.raises(HTTPException) as exc:
        power.execute_target_command("mainpc", "shutdown")
    assert exc.value.status_code == 503
    assert calls == ["uname -s", "probe-windows"]


def test_unavailable_os_logs_authentication_failure_and_probe_timeout(setup_power, monkeypatch):
    settings, events = setup_power

    def run(cmd, **kwargs):
        if cmd[-1] == "uname -s":
            return subprocess.CompletedProcess(cmd, 255, stdout="", stderr="Permission denied (publickey).\n")
        assert cmd[-1] == "probe-windows"
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(power.subprocess, "run", run)
    with pytest.raises(HTTPException) as exc:
        power.execute_target_command("mainpc", "shutdown")
    assert exc.value.status_code == 503
    assert events[-1]["probes"] == [
        {"os": "ubuntu", "alias": settings.ubuntu_ssh_alias, "rc": 255,
         "stdout": "", "stderr": "Permission denied (publickey)."},
        {"os": "windows", "alias": settings.windows_ssh_alias,
         "error": "timeout", "timeout": 2},
    ]


@pytest.mark.parametrize("failure,status", [
    ("wrong-token", 500), ("nonzero", 500), ("timeout", 504), ("oserror", 500),
])
@pytest.mark.parametrize("action,token", [
    ("shutdown", "SHUTDOWN_ACCEPTED_V1"), ("reboot", "REBOOT_ACCEPTED_V1"),
])
def test_power_failure_is_not_success_or_os_fallback(setup_power, monkeypatch, failure, status, action, token):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd[-1])
        if cmd[-1] == "uname -s":
            return completed("Linux")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
        if failure == "oserror":
            raise OSError("connection failed")
        return completed(token if failure == "nonzero" else token + " extra",
                         1 if failure == "nonzero" else 0)

    monkeypatch.setattr(power.subprocess, "run", run)
    with pytest.raises(HTTPException) as exc:
        power.execute_target_command("mainpc", action)
    assert exc.value.status_code == status
    assert calls == ["uname -s", "reboot-windows" if action == "reboot" else action]
    assert setup_power[1][-1]["detected_os"] == "ubuntu"


@pytest.mark.parametrize("enabled,name", [(False, "mainpc"), (True, "other")])
def test_legacy_power_commands_are_preserved(setup_power, monkeypatch, enabled, name):
    monkeypatch.setattr(power, "get_settings", lambda: replace(setup_power[0], ubuntu_boot_enabled=enabled))
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return completed("legacy output")

    monkeypatch.setattr(power.subprocess, "run", run)
    result = power.execute_target_command(name, "shutdown")
    assert result["ok"] is True
    assert "detected_os" not in result
    assert calls == [["legacy-shutdown"]]
