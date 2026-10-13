import time
from datetime import UTC, datetime
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
HOUR_S = 3600
DAY_S = 24 * HOUR_S


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


def _iso(ts: int | None) -> str | None:
    """Unix timestamp -> ISO 8601 string in UTC (None stays None)."""
    if not ts:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


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


@mcp.tool()
def list_failed_tasks(since_hours: int = 168, limit: int = 20) -> list[dict]:
    """Recent Proxmox tasks that did not finish with status OK (newest first).

    Covers backups (vzdump), start/stop, migrations etc. Tasks with warnings
    are included. Running tasks are ignored. Default window: last 7 days.
    """
    cutoff = time.time() - since_hours * HOUR_S
    failed = [
        t
        for t in _call("/cluster/tasks")
        if t.get("status") not in (None, "OK") and t.get("starttime", 0) >= cutoff
    ]
    failed.sort(key=lambda t: t.get("starttime", 0), reverse=True)
    return [
        {
            "node": t.get("node"),
            "task_type": t.get("type"),
            "target_id": t.get("id") or None,
            "user": t.get("user"),
            "started": _iso(t.get("starttime")),
            "ended": _iso(t.get("endtime")),
            "status": t.get("status"),
        }
        for t in failed[:limit]
    ]


def _backups_by_vmid(node: str, unreachable: list[str]) -> dict[int, list[int]]:
    """Collect backup creation times per VMID from all active backup storages."""
    result: dict[int, list[int]] = {}
    for st in _call(f"/nodes/{node}/storage", {"content": "backup"}):
        name = st["storage"]
        if not st.get("active", 0):
            unreachable.append(f"{node}/{name}")
            continue
        try:
            content = _call(
                f"/nodes/{node}/storage/{name}/content", {"content": "backup"}
            )
        except ToolError:
            unreachable.append(f"{node}/{name}")
            continue
        for item in content:
            if item.get("vmid") is not None and item.get("ctime"):
                result.setdefault(int(item["vmid"]), []).append(item["ctime"])
    return result


@mcp.tool()
def get_backup_status(max_age_hours: int = 24) -> dict:
    """Backup status per guest: newest backup, its age and number of backups.

    A guest is 'ok' if its newest backup is younger than max_age_hours.
    Guests without any backup are reported as not ok. Problems are listed
    first. Templates are skipped. Storages that are inactive or unreachable
    are listed separately, because backups on them could not be checked.
    """
    guests = [g for g in _guests() if not g.get("template", 0)]
    unreachable: list[str] = []
    backups: dict[int, list[int]] = {}
    for node in sorted({g["node"] for g in guests}):
        for vmid, times in _backups_by_vmid(node, unreachable).items():
            backups.setdefault(vmid, []).extend(times)

    now = time.time()
    result = []
    for g in guests:
        # set() removes duplicates from shared storages seen by several nodes
        times = sorted(set(backups.get(g["vmid"], [])))
        newest = times[-1] if times else None
        age_h = round((now - newest) / HOUR_S, 1) if newest else None
        result.append(
            {
                "vmid": g["vmid"],
                "name": g.get("name"),
                "type": g.get("type"),
                "node": g.get("node"),
                "last_backup": _iso(newest),
                "age_hours": age_h,
                "backup_count": len(times),
                "ok": age_h is not None and age_h <= max_age_hours,
            }
        )
    # not ok first, then oldest backup first (no backup counts as oldest)
    result.sort(key=lambda r: (r["ok"], -(r["age_hours"] or float("inf"))))
    return {
        "max_age_hours": max_age_hours,
        "guests": result,
        "unreachable_storages": unreachable,
    }


@mcp.tool()
def list_snapshots(vmid: int) -> list[dict]:
    """Snapshots of a VM or container with creation date and age (oldest first)."""
    guest = next((g for g in _guests() if g.get("vmid") == vmid), None)
    if guest is None:
        raise ToolError(f"No guest with VMID {vmid} found")
    snaps = _call(f"/nodes/{guest['node']}/{guest['type']}/{vmid}/snapshot")
    now = time.time()
    result = [
        {
            "name": s["name"],
            "created": _iso(s.get("snaptime")),
            "age_days": round((now - s["snaptime"]) / DAY_S, 1)
            if s.get("snaptime")
            else None,
            "description": (s.get("description") or "").strip() or None,
        }
        for s in snaps
        # "current" is not a snapshot but the live state of the guest
        if s.get("name") != "current"
    ]
    return sorted(result, key=lambda s: s["created"] or "")


@mcp.prompt()
def health_check(max_backup_age_hours: int = 24) -> str:
    """Create a health report of the Proxmox host using all read-only tools."""
    return f"""Create a short health report for my Proxmox VE environment.

Use the tools of the pve-readonly server:
1. list_nodes: are all nodes online? Flag CPU above 80 % or memory above 90 %.
2. list_storage: flag every storage above 85 % usage or with a status other
   than "available".
3. get_backup_status with max_age_hours={max_backup_age_hours}: list every guest
   that is not ok and every unreachable storage.
4. list_failed_tasks: summarise failed tasks of the last 7 days, grouped by type.

Format: start with an overall status (OK / WARNING / CRITICAL), then one
section per check. Only list problems in detail; summarise what is fine in one
line. End with up to three concrete next steps. Do not suggest changes you
cannot verify with the available read-only tools."""


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
