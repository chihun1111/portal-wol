import errno
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import targets


@pytest.mark.parametrize("content", [
    "", "{broken", "null", '{"targets": {}}', "\xff",
    '{"targets":[{"name":"mainpc","ip":"invalid"}]}',
    '{"targets":[{"name":"mainpc","ip":"192.0.2.10","mac":123}]}',
    '{"targets":[{"name":"mainpc","ip":"192.0.2.10","mac":"bad"}]}',
    '{"targets":[{"name":"mainpc","ip":"192.0.2.10"},{"name":"MainPC","ip":"192.0.2.20"}]}',
    '{"targets":[null]}', '{"mainpc":null}',
    '{"targets":[{"name":"mainpc","ip":"192.0.2.10","created_at":NaN}]}',
    '{"targets":[{"name":"mainpc","ip":"192.0.2.10","created_at":1e999}]}',
])
def test_corrupt_target_file_is_preserved(content):
    targets.TARGETS_FILE.write_text(content, encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        targets.list_targets()

    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "targets_file_invalid"
    assert targets.TARGETS_FILE.read_text(encoding="utf-8") == content


def test_invalid_utf8_target_file_is_preserved():
    targets.TARGETS_FILE.write_bytes(b"\xff")
    with pytest.raises(HTTPException) as exc:
        targets.list_targets()
    assert exc.value.status_code == 503
    assert targets.TARGETS_FILE.read_bytes() == b"\xff"


def test_legacy_targets_keep_command_fields():
    targets.TARGETS_FILE.write_text(json.dumps({"MainPC": {
        "ip": "192.0.2.10", "mac": "02-00-00-00-00-10", "reboot": ["example", "{ip}"],
    }}), encoding="utf-8")

    target = targets.get_target_or_404("mainpc")

    assert target["mac"] == "02:00:00:00:00:10"
    assert target["reboot"] == ["example", "{ip}"]
    assert json.loads(targets.TARGETS_FILE.read_text())["targets"][0] == target


@pytest.mark.parametrize("system,output", [
    ("Linux", "192.0.2.10 dev eth0 lladdr 02:00:00:00:00:10 REACHABLE\n"),
    ("Linux", "Address HWtype HWaddress Flags Mask Iface\n192.0.2.10 ether 02:00:00:00:00:10 C eth0\n"),
    ("Windows", "Interface: 192.0.2.1 --- 0x8\n  Internet Address Physical Address Type\n  192.0.2.10  02-00-00-00-00-10 dynamic\n"),
])
def test_mac_discovery_parses_actual_neighbor_rows(monkeypatch, system, output):
    monkeypatch.setattr(targets.platform, "system", lambda: system)
    monkeypatch.setattr(targets.subprocess, "run", lambda cmd, **kwargs:
                        subprocess.CompletedProcess(cmd, 0, output, ""))

    assert targets.discover_mac_for_ip("192.0.2.10") == "02:00:00:00:00:10"


@pytest.mark.parametrize("output", [
    "192.0.2.100 dev eth0 lladdr 02:00:00:00:00:10 REACHABLE",
    "192.0.2.10 dev eth0 lladdr ff:ff:ff:ff:ff:ff REACHABLE",
    "192.0.2.10 dev eth0 lladdr 00:00:00:00:00:00 REACHABLE",
    "192.0.2.10 dev eth0 lladdr 02:00:00:00:00:10:ab:cd REACHABLE",
    "192.0.2.10 dev eth0 INCOMPLETE",
])
def test_mac_discovery_rejects_unrelated_or_unusable_entries(monkeypatch, output):
    monkeypatch.setattr(targets.subprocess, "run", lambda cmd, **kwargs:
                        subprocess.CompletedProcess(cmd, 0, output, ""))
    assert targets.discover_mac_for_ip("192.0.2.10") is None


def test_configured_mac_skips_discovery(monkeypatch):
    monkeypatch.setattr(targets, "discover_mac_for_ip", lambda _ip: pytest.fail("MAC is already known"))
    targets.record_status("mainpc", True, "192.0.2.10")
    assert targets.list_targets()[0]["online"] is True


def test_status_for_old_ip_does_not_update_edited_target(monkeypatch):
    monkeypatch.setattr(targets, "discover_mac_for_ip", lambda _ip: pytest.fail("stale probe"))
    targets.update_target("mainpc", {"ip": "192.0.2.20"})
    targets.record_status("mainpc", True, "192.0.2.10")
    assert "online" not in targets.list_targets()[0]


def test_learning_does_not_overwrite_concurrent_manual_mac(monkeypatch):
    targets.update_target("mainpc", {"mac": ""})

    def discover(_ip):
        targets.update_target("mainpc", {"mac": "02:00:00:00:00:20"})
        return "02:00:00:00:00:10"

    monkeypatch.setattr(targets, "discover_mac_for_ip", discover)
    targets.record_status("mainpc", True, "192.0.2.10")
    assert targets.get_target_or_404("mainpc")["mac"] == "02:00:00:00:00:20"


def test_learning_does_not_apply_mac_after_ip_changes(monkeypatch):
    targets.update_target("mainpc", {"mac": ""})

    def discover(_ip):
        targets.update_target("mainpc", {"ip": "192.0.2.20"})
        return "02:00:00:00:00:10"

    monkeypatch.setattr(targets, "discover_mac_for_ip", discover)
    targets.record_status("mainpc", True, "192.0.2.10")
    target = targets.get_target_or_404("mainpc")
    assert target["ip"] == "192.0.2.20"
    assert "mac" not in target
    assert "online" not in targets.list_targets()[0]


def test_concurrent_creates_do_not_lose_targets():
    def create(index):
        return targets.create_target({"name": f"pc-{index}", "ip": f"192.0.2.{index + 20}"})

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(create, range(20)))

    assert len(targets.list_targets()) == 21
    assert len(json.loads(targets.TARGETS_FILE.read_text())["targets"]) == 21


def test_atomic_write_failure_preserves_previous_file(monkeypatch):
    before = targets.TARGETS_FILE.read_bytes()

    def fail_replace(*_args):
        raise OSError(errno.ENOSPC, "disk full")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        targets.update_target("mainpc", {"ip": "192.0.2.20"})
    assert targets.TARGETS_FILE.read_bytes() == before
    assert not list(targets.TARGETS_FILE.parent.glob(".targets.json.*.tmp"))


def test_bind_mounted_file_can_be_updated(monkeypatch):
    def mounted_file(*_args):
        raise OSError(errno.EBUSY, "device or resource busy")

    monkeypatch.setattr(Path, "replace", mounted_file)
    targets.update_target("mainpc", {"ip": "192.0.2.20"})
    assert json.loads(targets.TARGETS_FILE.read_text())["targets"][0]["ip"] == "192.0.2.20"
    assert not list(targets.TARGETS_FILE.parent.glob(".targets.json.*.tmp"))


def test_read_only_parent_with_writable_bind_mount_can_be_updated(monkeypatch):
    def read_only_directory(*_args, **_kwargs):
        raise OSError(errno.EROFS, "read-only directory")

    monkeypatch.setattr(targets.tempfile, "NamedTemporaryFile", read_only_directory)
    targets.update_target("mainpc", {"mac": None})
    assert "mac" not in json.loads(targets.TARGETS_FILE.read_text())["targets"][0]


def test_deleted_target_does_not_regain_runtime_state(monkeypatch):
    monkeypatch.setattr(targets, "discover_mac_for_ip", lambda _ip: pytest.fail("deleted target"))
    targets.delete_target("mainpc")
    targets.record_status("mainpc", True, "192.0.2.10")
    targets.record_wake("mainpc")
    assert targets._RUNTIME_STATE == {}


@pytest.mark.parametrize("error", [OSError("disk unavailable"), HTTPException(503, "invalid file")])
def test_wake_metadata_failure_does_not_turn_success_into_failure(monkeypatch, caplog, error):
    def unavailable():
        raise error

    monkeypatch.setattr(targets, "_load_state_locked", unavailable)
    targets.record_wake("mainpc")
    assert "Unable to record wake metadata" in caplog.text
