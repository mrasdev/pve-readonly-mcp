from functools import lru_cache

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from pve_readonly_mcp.config import load_settings
from pve_readonly_mcp.pve_client import PveClient, PveError

mcp = MCPServer(
    "pve-readonly",
    version="0.1.0",
    instructions="Read-only access to a Proxmox VE host. No changes are possible.",
)

GIB = 1024**3


@lru_cache(maxsize=1)
def get_client() -> PveClient:
    s = load_settings()
    return PveClient(s.base_url, s.token_id, s.token_secret, s.ca_file)


def _call(path: str, params: dict | None = None):
    try:
        return get_client().get(path, params)
    except (PveError, RuntimeError) as e:
        raise ToolError(str(e)) from e


def _gib(value: int | None) -> float:
    return round((value or 0) / GIB, 2)


def _guests() -> list[dict]:
    return _call("/cluster/resources", {"type": "vm"})


def _storages() -> list[dict]:
    return _call("/cluster/resources", {"type": "storage"})


@mcp.tool()
def list_nodes() -> list[dict]:
    """List all Proxmox nodes with status, CPU load, memory usage and uptime."""
    return [
        {
            "node": n["node"],
            "status": n.get("status"),
            "cpu_percent": round(n.get("cpu", 0) * 100, 1),
            "mem_used_gib": _gib(n.get("mem")),
            "mem_total_gib": _gib(n.get("maxmem")),
            "uptime_s": n.get("uptime", 0),
        }
        for n in _call("/nodes")
    ]


@mcp.tool()
def list_guests(node: str | None = None, status: str | None = None) -> list[dict]:
    """List virtual machines (qemu) and containers (lxc).

    Optionally filtered by node and status ('running' or 'stopped').
    """
    result = []
    for g in _guests():
        if node and g.get("node") != node:
            continue
        if status and g.get("status") != status:
            continue
        result.append(
            {
                "vmid": g["vmid"],
                "name": g.get("name"),
                "type": g.get("type"),
                "node": g.get("node"),
                "status": g.get("status"),
                "template": bool(g.get("template", 0)),
            }
        )
    return sorted(result, key=lambda g: g["vmid"])


@mcp.tool()
def get_guest_status(vmid: int) -> dict:
    """Current status of a VM or container: CPU, memory, uptime."""
    guest = next((g for g in _guests() if g.get("vmid") == vmid), None)
    if guest is None:
        raise ToolError(f"No guest with VMID {vmid} found")
    st = _call(f"/nodes/{guest['node']}/{guest['type']}/{vmid}/status/current")
    return {
        "vmid": vmid,
        "name": st.get("name"),
        "type": guest["type"],
        "node": guest["node"],
        "status": st.get("status"),
        "cpus": st.get("cpus"),
        "cpu_percent": round(st.get("cpu", 0) * 100, 1),
        "mem_used_gib": _gib(st.get("mem")),
        "mem_total_gib": _gib(st.get("maxmem")),
        "uptime_s": st.get("uptime", 0),
    }


@mcp.tool()
def list_storage(node: str | None = None) -> list[dict]:
    """Storage of one or all nodes: total, used, free, type, status, shared."""
    result = []
    for s in _storages():
        if node and s.get("node") != node:
            continue
        maxdisk_b = s.get("maxdisk") or 0
        disk_b = s.get("disk") or 0
        used_pct = round(disk_b / maxdisk_b * 100, 1) if maxdisk_b else 0.0
        result.append(
            {
                "storage": s["storage"],
                "node": s.get("node"),
                "type": s.get("plugintype"),
                "status": s.get("status"),
                "shared": bool(s.get("shared", 0)),
                "total_gib": _gib(maxdisk_b),
                "used_gib": _gib(disk_b),
                "free_gib": _gib(maxdisk_b - disk_b),
                "used_percent": used_pct,
            }
        )
    return sorted(result, key=lambda s: s["used_percent"], reverse=True)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
