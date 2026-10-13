"""Testet den Server so, wie ein MCP-Client ihn sieht (in-process, ohne stdio)."""

import pytest
from mcp import Client

from pve_readonly_mcp.server import mcp

pytestmark = pytest.mark.anyio


async def test_tools_are_listed():
    async with Client(mcp) as client:
        result = await client.list_tools()
    names = {t.name for t in result.tools}
    assert names == {"list_nodes", "list_guests", "get_guest_status"}


async def test_call_tool(fake_client):
    async with Client(mcp) as client:
        result = await client.call_tool("list_guests", {"status": "stopped"})
    assert not result.is_error
    assert result.structured_content["result"][0]["name"] == "win11"
