"""
rook.transport.mcp — MCP server (stdio transport)
====================================================
Exposes all Rook skills as MCP tools for Claude Desktop, Cursor, etc.

Usage:
    python -m rook.transport.mcp

Claude Desktop config:
    "rook": {
        "command": "ssh",
        "args": ["-T", "user@host", "cd /path/to/rook && venv/bin/python3 -m rook.transport.mcp"]
    }
"""

import asyncio
import json
import sys
import logging

from rook.core.config import cfg
from rook.core.db import init_db
from rook.skills.loader import load_skills, get_all_tools, execute_tool

logger = logging.getLogger(__name__)


async def handle_request(request: dict) -> dict:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "rook", "version": "0.1.0"},
            }
        }

    elif method == "notifications/initialized":
        return None  # No response for notifications

    elif method == "tools/list":
        tools = get_all_tools()
        mcp_tools = []
        for t in tools:
            mcp_tools.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "inputSchema": t.get("input_schema", {"type": "object", "properties": {}}),
            })
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": mcp_tools}
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = await execute_tool(tool_name, arguments)
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "content": [{"type": "text", "text": str(result)}],
                "isError": result.startswith("Error:") if isinstance(result, str) else False,
            }
        }

    elif method == "prompts/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}

    elif method == "resources/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}}

    else:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}
        }


async def main():
    """Run MCP server on stdio."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    init_db()
    skills = load_skills()
    tools = get_all_tools()

    print(f"Rook MCP server ready: {len(skills)} skills, {len(tools)} tools", file=sys.stderr)

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    buffer = ""
    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            text = line.decode("utf-8").strip()
            if not text:
                continue

            request = json.loads(text)
            response = await handle_request(request)

            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(f"MCP error: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
