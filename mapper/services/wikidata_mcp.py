"""
MCP client for the official Wikidata MCP, hosted by Wikimedia Deutschland
(https://www.wikidata.org/wiki/Wikidata:MCP). Optional and complementary to the
live property search (mapper/services/wikidata_api.py).

Unlike a local MCP server over stdio, this is a remote endpoint ("streamable
HTTP" transport), so there is no process to start: just an HTTP call mediated
by the MCP protocol.
"""

import asyncio

from django.conf import settings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def _call_tool_async(tool_name: str, args: dict):
    async with streamable_http_client(settings.WD_MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            return result


def find_candidates_mcp(query: str, language: str, top_n: int = 5) -> list[dict]:
    """Searches Wikidata properties through the Wikidata MCP search_properties tool.

    Returns a list of dicts {"pid": ..., "label": ..., "description": ...}.
    Raises RuntimeError if USE_WD_MCP is off or if the service does not respond.
    """
    if not settings.USE_WD_MCP:
        raise RuntimeError("USE_WD_MCP is turned off in the settings.")

    result = asyncio.run(
        _call_tool_async(
            "search_properties",
            {"query": query, "lang": language, "include_external_ids": False},
        )
    )

    # The actual response is a single text in structured_content["result"],
    # with one property per line in the format "PID: label — description".
    text = ""
    if result.structured_content:
        text = result.structured_content.get("result", "")
    if not text:
        text = "".join(
            block.text for block in result.content if hasattr(block, "text")
        )

    candidates = []
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        pid, _, rest = line.partition(":")
        label, _, description = rest.strip().partition(" — ")
        candidates.append(
            {
                "pid": pid.strip(),
                "label": label.strip(),
                "description": description.strip(),
            }
        )

    return candidates[:top_n]
