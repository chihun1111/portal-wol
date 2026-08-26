from types import SimpleNamespace

from app.services import power


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
        ),
    )
    monkeypatch.setattr(power, "get_target_or_404", lambda _name: target)
    monkeypatch.setattr(power, "send_magic_packet", lambda mac, dst: packets.append((mac, dst)))
    monkeypatch.setattr(power, "log_event", events.append)
    monkeypatch.setattr(power, "record_wake", lambda _name: None)

    result = power.wake_target("mainpc")

    assert packets == [("10:FF:E0:66:47:E9", "192.168.123.255")]
    assert result["destination"] == "192.168.123.255"
    assert events[0]["destination"] == "192.168.123.255"
