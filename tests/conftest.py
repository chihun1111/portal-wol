import json

import pytest

from app.core.settings import get_settings
from app.services import targets


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Tests must never edit configured PCs or production logs/job history."""
    target_file = tmp_path / "targets.json"
    target_file.write_text(json.dumps({"targets": [{
        "name": "mainpc", "ip": "192.0.2.10", "mac": "02:00:00:00:00:10",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }]}), encoding="utf-8")
    monkeypatch.setattr(targets, "TARGETS_FILE", target_file)
    monkeypatch.setattr(targets, "_RUNTIME_STATE", {})
    monkeypatch.setenv("LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("BOOT_DB_PATH", str(tmp_path / "boot-jobs.sqlite3"))
    monkeypatch.setenv("UBUNTU_BOOT_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
