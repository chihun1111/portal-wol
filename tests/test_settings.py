import math

import pytest

from app.core.settings import get_settings


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "invalid"])
def test_non_finite_intervals_use_defaults(monkeypatch, value):
    monkeypatch.setenv("WOL_PACKET_INTERVAL", value)
    monkeypatch.setenv("BOOT_POLL_INTERVAL", value)
    settings = get_settings()
    assert settings.wol_packet_interval == 0.25
    assert settings.boot_poll_interval == 5
    assert math.isfinite(settings.boot_poll_interval)


def test_invalid_bounds_cannot_disable_timeouts_or_spin_polling(monkeypatch):
    for key in ("WINDOWS_READY_TIMEOUT", "UBUNTU_READY_TIMEOUT", "BOOT_JOB_TIMEOUT",
                "SSH_COMMAND_TIMEOUT", "REBOOT_START_TIMEOUT", "LOG_MAX_LIMIT"):
        monkeypatch.setenv(key, "0")
    monkeypatch.setenv("BOOT_POLL_INTERVAL", "-1")
    monkeypatch.setenv("UBUNTU_BOOT_TARGET", " MainPC ")
    settings = get_settings()
    assert settings.windows_ready_timeout == 1
    assert settings.ubuntu_ready_timeout == 1
    assert settings.boot_job_timeout == 1
    assert settings.ssh_command_timeout == 1
    assert settings.reboot_start_timeout == 1
    assert settings.log_max_limit == 1
    assert settings.boot_poll_interval == 0.1
    assert settings.ubuntu_boot_target == "mainpc"
