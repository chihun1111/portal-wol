from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH_HEADERS = {"Tailscale-User-Login": "tester@example.com"}


def test_root_redirects_to_wol():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/wol"


def test_static_pages_are_available():
    assert client.get("/wol").status_code == 200
    assert client.get("/settings").status_code == 200


def test_legacy_html_paths_redirect_to_canonical_pages():
    wol_response = client.get("/wol.html", follow_redirects=False)
    settings_response = client.get("/settings.html", follow_redirects=False)

    assert wol_response.status_code == 307
    assert wol_response.headers["location"] == "/wol"
    assert settings_response.status_code == 307
    assert settings_response.headers["location"] == "/settings"


def test_targets_api_is_accessible():
    response = client.get("/api/targets", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert "targets" in response.json()


def test_api_requires_tailscale_identity():
    response = client.get("/api/targets")
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "tailscale_identity_required"


def test_health_check_does_not_require_identity():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
