import subprocess
from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.services import power
from app.core.settings import get_settings


@pytest.fixture(autouse=True)
def legacy_power_settings(monkeypatch):
    settings = replace(get_settings(), ubuntu_boot_enabled=False)
    monkeypatch.setattr(power, "get_settings", lambda: settings)


def test_execute_target_command_renders_ip_placeholder(monkeypatch):
    target = {
        "name": "mainpc",
        "ip": "192.168.123.175",
        "shutdown": ["ssh", "wolsvc@{ip}", "powershell", "Stop-Computer", "-Force"],
    }
    captured = {}

    def fake_get_target_or_404(_name):
        return target

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(power, "get_target_or_404", fake_get_target_or_404)
    monkeypatch.setattr(power.subprocess, "run", fake_run)

    result = power.execute_target_command("mainpc", "shutdown")

    assert result["ok"] is True
    assert captured["cmd"][1] == "wolsvc@192.168.123.175"


def test_execute_target_command_fails_when_placeholder_has_no_value(monkeypatch):
    target = {
        "name": "mainpc",
        "shutdown": ["ssh", "wolsvc@{ip}", "powershell", "Stop-Computer", "-Force"],
    }

    monkeypatch.setattr(power, "get_target_or_404", lambda _name: target)

    with pytest.raises(HTTPException) as exc_info:
        power.execute_target_command("mainpc", "shutdown")

    assert exc_info.value.status_code == 400
    assert "placeholder {ip}" in str(exc_info.value.detail)
