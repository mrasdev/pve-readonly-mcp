import time

import httpx
import pytest

from pve_readonly_mcp import server
from pve_readonly_mcp.pve_client import PveClient

NOW = int(time.time())
HOUR = 3600
DAY = 24 * HOUR

# Responses based on the Proxmox API documentation (excerpt). Verify against
# a real host with `pvesh get <path> --output-format json`.
FAKE_API = {
    "/api2/json/nodes": [
        {
            "node": "pve",
            "status": "online",
            "cpu": 0.0523,
            "mem": 8 * 1024**3,
            "maxmem": 32 * 1024**3,
            "uptime": 86400,
        }
    ],
    "/api2/json/cluster/resources": [
        {
            "vmid": 101,
            "name": "prometheus",
            "type": "lxc",
            "node": "pve",
            "status": "running",
            "template": 0,
        },
        {
            "vmid": 100,
            "name": "win11",
            "type": "qemu",
            "node": "pve",
            "status": "stopped",
            "template": 0,
        },
        {
            "type": "storage",
            "storage": "local",
            "plugintype": "dir",
            "node": "pve",
            "status": "available",
            "shared": 0,
            "maxdisk": 100 * 1024**3,
            "disk": 25 * 1024**3,
        },
        {
            "type": "storage",
            "storage": "local-lvm",
            "plugintype": "lvmthin",
            "node": "pve",
            "status": "available",
            "shared": 0,
            "maxdisk": 200 * 1024**3,
            "disk": 150 * 1024**3,
        },
        {
            "type": "storage",
            "storage": "nas",
            "plugintype": "nfs",
            "node": "pve",
            "status": "unknown",
            "shared": 1,
        },
    ],
    "/api2/json/nodes/pve/lxc/101/status/current": {
        "name": "prometheus",
        "status": "running",
        "cpus": 2,
        "cpu": 0.1,
        "mem": 512 * 1024**2,
        "maxmem": 2 * 1024**3,
        "uptime": 3600,
    },
    # Tasks: one OK, one failed backup, one with warnings, one running,
    # one failed but older than 7 days
    "/api2/json/cluster/tasks": [
        {
            "node": "pve",
            "type": "vzdump",
            "id": "101",
            "user": "root@pam",
            "starttime": NOW - 2 * HOUR,
            "endtime": NOW - 2 * HOUR + 60,
            "status": "OK",
        },
        {
            "node": "pve",
            "type": "vzdump",
            "id": "100",
            "user": "root@pam",
            "starttime": NOW - 3 * HOUR,
            "endtime": NOW - 3 * HOUR + 30,
            "status": "job errors",
        },
        {
            "node": "pve",
            "type": "aptupdate",
            "id": "",
            "user": "root@pam",
            "starttime": NOW - 1 * DAY,
            "endtime": NOW - 1 * DAY + 20,
            "status": "WARNINGS: 1",
        },
        {
            "node": "pve",
            "type": "vncproxy",
            "id": "100",
            "user": "root@pam",
            "starttime": NOW - 60,
        },
        {
            "node": "pve",
            "type": "qmstart",
            "id": "100",
            "user": "root@pam",
            "starttime": NOW - 10 * DAY,
            "endtime": NOW - 10 * DAY + 5,
            "status": "start failed",
        },
    ],
    # Storages of node pve that may hold backups (?content=backup)
    "/api2/json/nodes/pve/storage": [
        {"storage": "local", "active": 1, "content": "backup,iso,vztmpl"},
        {"storage": "pbs", "active": 1, "content": "backup"},
        {"storage": "nas", "active": 0, "content": "backup"},
    ],
    # "pbs" is missing on purpose: the mock answers 404 -> unreachable
    "/api2/json/nodes/pve/storage/local/content": [
        {
            "volid": "local:backup/vzdump-lxc-101-new.tar.zst",
            "vmid": 101,
            "ctime": NOW - 2 * HOUR,
            "content": "backup",
        },
        {
            "volid": "local:backup/vzdump-lxc-101-old.tar.zst",
            "vmid": 101,
            "ctime": NOW - 2 * DAY,
            "content": "backup",
        },
        {
            "volid": "local:backup/vzdump-qemu-100.vma.zst",
            "vmid": 100,
            "ctime": NOW - 3 * DAY,
            "content": "backup",
        },
    ],
    "/api2/json/nodes/pve/lxc/101/snapshot": [
        {
            "name": "before-upgrade",
            "snaptime": NOW - 40 * DAY,
            "description": "pre 8.2 upgrade\n",
        },
        {"name": "weekly", "snaptime": NOW - 2 * DAY, "description": ""},
        {"name": "current", "description": "You are here!", "parent": "weekly"},
    ],
}

RESOURCE_TYPES = {"vm": {"qemu", "lxc"}, "storage": {"storage"}}


def fake_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "PVEAPIToken=test@pve!ro=secret"
    assert request.method == "GET"  # read-only: never anything other than GET
    data = FAKE_API.get(request.url.path)
    if data is None:
        return httpx.Response(404, json={"data": None})
    if request.url.path == "/api2/json/cluster/resources":
        # intentionally strict: missing type will raise KeyError
        wanted = RESOURCE_TYPES[request.url.params.get("type")]
        data = [r for r in data if r["type"] in wanted]
    return httpx.Response(200, json={"data": data})


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch):
    client = PveClient(
        "https://pve.test:8006/api2/json",
        "test@pve!ro",
        "secret",
        transport=httpx.MockTransport(fake_handler),
    )
    monkeypatch.setattr(server, "get_client", lambda: client)
    return client


@pytest.fixture
def anyio_backend():
    return "asyncio"
