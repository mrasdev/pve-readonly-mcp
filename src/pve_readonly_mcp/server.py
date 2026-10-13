from functools import lru_cache

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from pve_readonly_mcp.config import load_settings
from pve_readonly_mcp.pve_client import PveClient, PveError

mcp = MCPServer(
    "pve-readonly",
    version="0.1.0",
    instructions="Nur lesender Zugriff auf einen Proxmox-VE-Host. Keine Änderungen möglich.",
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


@mcp.tool()
def list_nodes() -> list[dict]:
    """Listet alle Proxmox-Knoten mit Status, CPU-Last, RAM-Nutzung und Uptime."""
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
    """Listet VMs (qemu) und Container (lxc).

    Optional gefiltert nach Knoten und Status ('running' oder 'stopped').
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
    """Aktueller Status einer VM bzw. eines Containers: CPU, RAM, Uptime."""
    guest = next((g for g in _guests() if g.get("vmid") == vmid), None)
    if guest is None:
        raise ToolError(f"Kein Gast mit VMID {vmid} gefunden")
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
