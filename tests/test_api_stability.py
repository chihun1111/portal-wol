import asyncio
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import create_app


AUTH_HEADERS = {"Tailscale-User-Login": "tester@example.com"}


@pytest.mark.parametrize("operation", ["status", "wake", "shutdown", "reboot"])
def test_health_remains_responsive_during_blocking_device_io(monkeypatch, operation):
    entered = threading.Event()
    released = threading.Event()
    finished = threading.Event()

    def blocked_operation(*_args, **_kwargs):
        entered.set()
        released.wait(3)
        finished.set()
        return True if operation == "status" else {"ok": True}

    monkeypatch.setattr(routes, "probe_online", blocked_operation)
    monkeypatch.setattr(routes, "wake_target", blocked_operation)
    monkeypatch.setattr(routes, "execute_target_command", blocked_operation)

    async def check():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=AUTH_HEADERS) as client:
            request = (client.get("/api/status?target=mainpc&silent=true") if operation == "status"
                       else client.post(f"/api/{operation}", json={"target": "mainpc"}))
            pending = asyncio.create_task(request)
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert not finished.is_set(), "device I/O blocked the event loop"
                health = await asyncio.wait_for(client.get("/healthz"), timeout=1)
                assert health.status_code == 200
                assert not finished.is_set(), "health waited for the device operation"
            finally:
                released.set()
                response = await pending
            assert response.status_code == 200

    asyncio.run(check())


def test_conflicting_power_and_target_edits_are_rejected_before_side_effects(monkeypatch):
    app = create_app()
    monkeypatch.setattr(routes, "wake_target", lambda *_: pytest.fail("reserved target"))
    monkeypatch.setattr(routes, "execute_target_command", lambda *_: pytest.fail("reserved target"))
    with TestClient(app) as client, app.state.boot_jobs.power_action("mainpc"):
        for operation in ("wake", "shutdown", "reboot"):
            response = client.post(f"/api/{operation}", headers=AUTH_HEADERS, json={"target": " MainPC "})
            assert response.status_code == 409
            assert response.json()["detail"]["error"] == "target_busy"
        assert client.patch("/api/targets/mainpc", headers=AUTH_HEADERS,
                            json={"ip": "192.0.2.20"}).status_code == 409
        assert client.delete("/api/targets/mainpc", headers=AUTH_HEADERS).status_code == 409


def test_target_crud_preserves_omitted_mac_and_clears_explicit_null():
    with TestClient(create_app()) as client:
        created = client.post("/api/targets", headers=AUTH_HEADERS, json={
            "name": "second-pc", "ip": "192.0.2.20", "mac": "02:00:00:00:00:20",
        })
        assert created.status_code == 200
        updated = client.patch("/api/targets/second-pc", headers=AUTH_HEADERS, json={"name": "renamed-pc"})
        assert updated.json()["target"]["mac"] == "02:00:00:00:00:20"
        cleared = client.patch("/api/targets/renamed-pc", headers=AUTH_HEADERS, json={"mac": None})
        assert cleared.status_code == 200
        assert "mac" not in cleared.json()["target"]
        assert client.delete("/api/targets/renamed-pc", headers=AUTH_HEADERS).status_code == 200
        names = [target["name"] for target in client.get("/api/targets", headers=AUTH_HEADERS).json()["targets"]]
        assert names == ["mainpc"]
