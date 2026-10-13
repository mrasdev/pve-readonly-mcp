from mcp.server.mcpserver import MCPServer

mcp = MCPServer("pve-readonly", version="0.1.0")


@mcp.tool()
def ping() -> str:
    """Prüft, ob der MCP-Server läuft."""
    return "pong"


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
