"""End-to-end demo: starts the MCP server as a separate process (exactly like Claude Desktop does, over
stdin/stdout), then calls a few tools against a running MM Store and prints what an AI would receive.

    MMSTORE_URL=http://localhost:8000 MMSTORE_EMAIL=... MMSTORE_PASSWORD=... python examples/demo.py
"""
import asyncio
import json
import os
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def main() -> None:
    server = StdioServerParameters(command=sys.executable, args=["-m", "mmstore_ai"], env=dict(os.environ))
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
        print(f"Connected to {client.server_info.name}: {len(tools)} tools ->", ", ".join(t.name for t in tools), "\n")
        for name, args in [("search_products", {"category": "pochettes"}),
                           ("resellers_overview", {}),
                           ("reseller_unpaid", {"reseller": "phone house"}),
                           ("sales_report", {})]:
            result = await client.call_tool(name, args)
            text = result.content[0].text
            print(f"### {name}({json.dumps(args, ensure_ascii=False)})")
            print(text if result.is_error else json.dumps(json.loads(text), ensure_ascii=False, indent=2)[:1200], "\n")


asyncio.run(main())
