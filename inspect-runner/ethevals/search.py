"""Run capped Exa tools on the host."""
import json
import os
import logging
import math
from pathlib import Path

import anyio
import httpx
from inspect_ai.tool import ToolDef, ToolParams
from inspect_ai.util import store


EXA_URL = "https://mcp.exa.ai/mcp"
TOOLS = json.loads(Path(__file__).with_name("exa-tools.json").read_text())
CAP_MESSAGE = "Search failed: epoch search cap reached."
RESULT_CAP = 10
URL_CAP = 5
CAP_DESCRIPTION = " Runner limits: numResults is clamped to 1–10 whole results, default 10. Fetch accepts at most 5 URLs per call; larger batches are rejected."


async def exa_request(url, name, arguments, key):
    """Call hosted MCP from the host. Credentials never enter tool arguments."""
    headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}
    if key:
        headers["x-api-key"] = key
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=False) as client:
        response = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                               "params": {"name": name, "arguments": arguments}})
        if response.is_error:
            logging.getLogger(__name__).warning("Exa HTTP status %s", response.status_code)
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            messages = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith("data:")]
            payload = next(message for message in messages if message.get("id") == 1)
        else:
            payload = response.json()
        if "error" in payload:
            error = json.dumps(payload["error"], ensure_ascii=True)
            logging.getLogger(__name__).warning("Exa JSON-RPC error: %s", error.replace(key, "[redacted]") if key else error)
            return {"isError": True, "content": [{"type": "text", "text": "Search failed at Exa."}]}
        return payload["result"]


def exa_tool(definition, url, limit):
    async def execute(**arguments) -> str:
        if definition["name"] == "web_search_exa":
            count = arguments.get("numResults", RESULT_CAP)
            if not isinstance(count, (int, float)) or not math.isfinite(count):
                return "Search failed: numResults must be finite."
            arguments["numResults"] = max(1, min(RESULT_CAP, int(count)))
        elif len(arguments.get("urls", [])) > URL_CAP:
            return "Search failed: at most 5 URLs are allowed per call."
        used = store().get("exa_calls", 0)
        if used >= limit:
            return CAP_MESSAGE
        # Reserve before the await. Failed or cancelled requests also consume a slot.
        store().set("exa_calls", used + 1)
        key = os.environ.get("EXA_API_KEY", "")
        try:
            with anyio.fail_after(30):
                result = await exa_request(url, definition["name"], arguments, key)
            text = "\n".join(item.get("text", "") for item in result.get("content", []))
            error = result.get("isError", False)
            if error:
                text = "Search failed: " + text
            return text.replace(key, "[redacted]") if key else text
        except httpx.HTTPStatusError as error:
            return "Search failed: Exa rate limit exceeded." if error.response.status_code == 429 else "Search failed: Exa request failed."
        except Exception:
            return "Search failed: Exa request failed."
    return ToolDef(execute, name=definition["name"], description=definition["description"] + CAP_DESCRIPTION,
                   parameters=ToolParams.model_validate(definition["inputSchema"])).as_tool()


def exa_tools(limit):
    return [exa_tool(definition, EXA_URL, limit) for definition in TOOLS]
