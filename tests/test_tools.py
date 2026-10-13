import pytest
from mcp.server.mcpserver.exceptions import ToolError

from pve_readonly_mcp import server


def test_list_nodes(fake_client):
    nodes = server.list_nodes()
    assert nodes == [
        {
            "node": "pve",
            "status": "online",
            "cpu_percent": 5.2,
            "mem_used_gib": 8.0,
            "mem_total_gib": 32.0,
            "uptime_s": 86400,
        }
    ]


def test_list_guests_sorted(fake_client):
    assert [g["vmid"] for g in server.list_guests()] == [100, 101]


def test_list_guests_filter_status(fake_client):
    guests = server.list_guests(status="running")
    assert [g["name"] for g in guests] == ["prometheus"]


def test_get_guest_status(fake_client):
    st = server.get_guest_status(101)
    assert st["type"] == "lxc"
    assert st["mem_used_gib"] == 0.5
    assert st["cpu_percent"] == 10.0


def test_get_guest_status_unknown_vmid(fake_client):
    with pytest.raises(ToolError, match="VMID 999"):
        server.get_guest_status(999)


def test_missing_config(monkeypatch):
    for var in ("PVE_URL", "PVE_TOKEN_ID", "PVE_TOKEN_SECRET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("pve_readonly_mcp.config.load_dotenv", lambda **kw: None)
    server.get_client.cache_clear()
    with pytest.raises(ToolError, match="PVE_URL is not set"):
        server.list_nodes()


def test_storage_values(fake_client):
    storages = server.list_storage()
    local = next(s for s in storages if s["storage"] == "local")
    assert local == {
        "storage": "local",
        "type": "dir",
        "node": "pve",
        "status": "available",
        "shared": False,
        "total_gib": 100.0,
        "used_gib": 25.0,
        "free_gib": 75.0,
        "used_percent": 25.0,
    }


def test_storage_sorting(fake_client):
    storages = server.list_storage()
    assert [s["storage"] for s in storages] == ["local-lvm", "local", "nas"]


def test_storage_filter_node(fake_client):
    assert len(server.list_storage(node="pve")) == 3
    assert server.list_storage(node="unknown") == []


def test_storage_missing_size(fake_client):
    storages = server.list_storage()
    nas = next(s for s in storages if s["storage"] == "nas")
    assert nas == {
        "storage": "nas",
        "type": "nfs",
        "node": "pve",
        "status": "unknown",
        "shared": True,
        "total_gib": 0.0,
        "used_gib": 0.0,
        "free_gib": 0.0,
        "used_percent": 0.0,
    }


def test_list_failed_tasks(fake_client):
    tasks = server.list_failed_tasks()
    # newest first; OK, running and too old tasks are excluded
    assert [t["status"] for t in tasks] == ["job errors", "WARNINGS: 1"]
    assert tasks[0]["task_type"] == "vzdump"
    assert tasks[0]["target_id"] == "100"
    assert tasks[1]["target_id"] is None


def test_list_failed_tasks_window_and_limit(fake_client):
    assert len(server.list_failed_tasks(since_hours=24 * 30)) == 3
    assert len(server.list_failed_tasks(limit=1)) == 1


def test_get_backup_status(fake_client):
    report = server.get_backup_status()
    guests = {g["vmid"]: g for g in report["guests"]}
    assert guests[101]["ok"] is True
    assert guests[101]["age_hours"] == 2.0
    assert guests[101]["backup_count"] == 2
    assert guests[100]["ok"] is False
    assert guests[100]["age_hours"] == 72.0
    # problems first
    assert [g["vmid"] for g in report["guests"]] == [100, 101]


def test_get_backup_status_threshold(fake_client):
    report = server.get_backup_status(max_age_hours=96)
    assert all(g["ok"] for g in report["guests"])


def test_get_backup_status_unreachable_storages(fake_client):
    report = server.get_backup_status()
    # nas is inactive, pbs answers with an error
    assert sorted(report["unreachable_storages"]) == ["pve/nas", "pve/pbs"]


def test_list_snapshots(fake_client):
    snaps = server.list_snapshots(101)
    # oldest first, pseudo snapshot "current" excluded
    assert [s["name"] for s in snaps] == ["before-upgrade", "weekly"]
    assert snaps[0]["age_days"] == 40.0
    assert snaps[0]["description"] == "pre 8.2 upgrade"
    assert snaps[1]["description"] is None


def test_list_snapshots_unknown_vmid(fake_client):
    with pytest.raises(ToolError, match="VMID 999"):
        server.list_snapshots(999)
