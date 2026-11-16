import subprocess
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import power
from app.services.boot_jobs import BootJobManager


def test_wake_target_uses_and_reports_configured_broadcast(monkeypatch):
    target = {
        "name": "mainpc",
        "ip": "192.168.123.175",
        "mac": "10:FF:E0:66:47:E9",
    }
    packets = []
    events = []

    monkeypatch.setattr(
        power,
        "get_settings",
        lambda: SimpleNamespace(
            wol_method="python",
            broadcast="192.168.123.255",
            lan_iface="enp6s18",
            wol_packet_count=5,
            wol_packet_interval=0.25,
        ),
    )
    monkeypatch.setattr(power, "get_target_or_404", lambda _name: target)
    monkeypatch.setattr(
        power,
        "send_magic_packet",
        lambda mac, dst, packet_count, packet_interval: packets.append(
            (mac, dst, packet_count, packet_interval)
        ),
    )
    monkeypatch.setattr(power, "log_event", events.append)
    monkeypatch.setattr(power, "record_wake", lambda _name: None)

    result = power.wake_target("mainpc")

    assert packets == [("10:FF:E0:66:47:E9", "192.168.123.255", 5, 0.25)]
    assert result["destination"] == "192.168.123.255"
    assert result["packet_count"] == 5
    assert events[0]["destination"] == "192.168.123.255"
    assert events[0]["packet_count"] == 5


def test_send_magic_packet_sends_configured_burst(monkeypatch):
    sent = []
    sleeps = []

    class FakeSocket:
        def setsockopt(self, *_args):
            pass

        def sendto(self, packet, destination):
            sent.append((packet, destination))

        def close(self):
            pass

    monkeypatch.setattr(power.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(power.time, "sleep", sleeps.append)

    power.send_magic_packet(
        "10:FF:E0:66:47:E9",
        "192.168.123.255",
        packet_count=5,
        packet_interval=0.25,
    )

    assert len(sent) == 5
    assert all(destination == ("192.168.123.255", 9) for _, destination in sent)
    assert sleeps == [0.25, 0.25, 0.25, 0.25]


@pytest.fixture
def etherwake_setup(monkeypatch):
    events = []
    recorded = []
    monkeypatch.setattr(power, "get_settings", lambda: SimpleNamespace(
        wol_method="etherwake", lan_iface="eth-test",
    ))
    monkeypatch.setattr(power, "get_target_or_404", lambda _name: {
        "name": "mainpc", "mac": "02:00:00:00:00:10",
    })
    monkeypatch.setattr(power, "log_event", events.append)
    monkeypatch.setattr(power, "record_wake", recorded.append)
    monkeypatch.setattr(power, "send_magic_packet", lambda *_args, **_kwargs: pytest.fail("no fallback packet"))
    return events, recorded


def test_etherwake_is_bounded_and_reports_success(etherwake_setup, monkeypatch):
    calls = []

    def call(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return 0

    monkeypatch.setattr(power.subprocess, "call", call)
    result = power.wake_target("MAINPC")

    assert calls == [(
        ["/usr/sbin/etherwake", "-i", "eth-test", "02:00:00:00:00:10"],
        {"timeout": power.DEFAULT_COMMAND_TIMEOUT_SEC},
    )]
    assert result == {
        "ok": True, "sent": "etherwake", "target": "mainpc",
        "destination": "eth-test", "packet_count": 1,
    }
    events, recorded = etherwake_setup
    assert events[0]["method"] == "etherwake"
    assert recorded == ["mainpc"]


@pytest.mark.parametrize("failure,status,detail", [
    ("timeout", 504, "etherwake command timed out"),
    ("missing", 500, "etherwake command failed to start"),
    ("permission", 500, "etherwake command failed to start"),
    ("nonzero", 500, "etherwake failed"),
])
def test_etherwake_errors_release_target_without_success_metadata(
    etherwake_setup, monkeypatch, failure, status, detail,
):
    def call(cmd, **kwargs):
        assert kwargs["timeout"] == power.DEFAULT_COMMAND_TIMEOUT_SEC
        if failure == "timeout":
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
        if failure == "missing":
            raise FileNotFoundError("etherwake missing")
        if failure == "permission":
            raise PermissionError("etherwake permission denied")
        return 1

    monkeypatch.setattr(power.subprocess, "call", call)
    manager = BootJobManager()
    with pytest.raises(HTTPException) as exc_info:
        with manager.power_action("mainpc") as target:
            power.wake_target(target)

    assert exc_info.value.status_code == status
    assert exc_info.value.detail == detail
    assert etherwake_setup == ([], [])
    with manager.power_action("mainpc"):
        pass
