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
