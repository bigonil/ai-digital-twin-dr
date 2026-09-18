"""
Entry point for MCP server: python -m mcp_server
"""
import asyncio
from .app import main

if __name__ == "__main__":
    asyncio.run(main())
