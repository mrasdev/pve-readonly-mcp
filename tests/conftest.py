import httpx
import pytest

from pve_readonly_mcp import server
from pve_readonly_mcp.pve_client import PveClient

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
}


def fake_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "PVEAPIToken=test@pve!ro=secret"
    assert request.method == "GET"  # read-only: never anything other than GET
    data = FAKE_API.get(request.url.path)
    if data is None:
        return httpx.Response(404, json={"data": None})
    return httpx.Response(200, json={"data": data})


@pytest.fixture
def fake_client(monkeypatch):
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
