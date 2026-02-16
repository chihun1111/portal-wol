from app import config


def test_probe_online_uses_ping_first(monkeypatch):
    monkeypatch.setattr(config, "ping_once", lambda _ip: True)
    monkeypatch.setattr(config, "tcp_port_open", lambda *_args, **_kwargs: False)
    assert config.probe_online("192.168.0.10", ports=(3389,))


def test_probe_online_falls_back_to_tcp(monkeypatch):
    monkeypatch.setattr(config, "ping_once", lambda _ip: False)
    monkeypatch.setattr(config, "tcp_port_open", lambda _ip, port, timeout_sec=1.0: port == 3389)
    assert config.probe_online("192.168.0.10", ports=(3389, 22))


def test_probe_online_returns_false_when_all_checks_fail(monkeypatch):
    monkeypatch.setattr(config, "ping_once", lambda _ip: False)
    monkeypatch.setattr(config, "tcp_port_open", lambda *_args, **_kwargs: False)
    assert not config.probe_online("192.168.0.10", ports=(3389, 22))
