"""Test the server the way an MCP client sees it (in-process, no stdio)."""

import pytest
from mcp import Client

from pve_readonly_mcp.server import mcp

pytestmark = pytest.mark.anyio


async def test_tools_are_listed():
    async with Client(mcp) as client:
        result = await client.list_tools()
    names = {t.name for t in result.tools}
    assert names == {
        "list_nodes",
        "list_guests",
        "get_guest_status",
        "list_storage",
        "list_failed_tasks",
        "get_backup_status",
        "list_snapshots",
    }


async def test_call_tool(fake_client):
    async with Client(mcp) as client:
        result = await client.call_tool("list_guests", {"status": "stopped"})
    assert not result.is_error
    assert result.structured_content["result"][0]["name"] == "win11"


async def test_health_check_prompt():
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        assert [p.name for p in prompts.prompts] == ["health_check"]
        result = await client.get_prompt("health_check", {"max_backup_age_hours": "48"})
    text = result.messages[0].content.text
    assert "max_age_hours=48" in text
    assert "list_storage" in text
