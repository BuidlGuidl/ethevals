"""Read Exa results from native MCP and Codex code-mode transcripts."""
import json
import re
import os

import anyio
import httpx
from inspect_ai.tool import tool
from inspect_ai.util import store


async def exa_request(url, arguments, key):
    """Call hosted MCP from the host. Credentials never enter tool arguments."""
    headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}
    if key:
        headers["x-api-key"] = key
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=False) as client:
        response = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                               "params": {"name": "web_search_exa", "arguments": arguments}})
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            messages = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith("data:")]
            payload = next(message for message in messages if message.get("id") == 1)
        else:
            payload = response.json()
        if "error" in payload:
            return {"isError": True, "content": [{"type": "text", "text": "Search failed at Exa."}]}
        return payload["result"]


@tool
def web_search_exa(url: str, limit: int):
    async def execute(query: str, numResults: int = 5) -> str:
        """Search the web using Exa.

        Args:
            query: Search query.
            numResults: Number of results, from one to five.
        """
        used = store().get("exa_calls", 0)
        if used >= limit:
            return "Search failed: epoch search rate limit exceeded."
        if not 1 <= numResults <= 5:
            return "Search failed: numResults must be between one and five."
        # Reserve before the await. Failed or cancelled requests also consume a slot.
        store().set("exa_calls", used + 1)
        key = os.environ.get("EXA_API_KEY", "")
        try:
            with anyio.fail_after(30):
                result = await exa_request(url, {"query": query, "numResults": numResults, "type": "auto"}, key)
            text, error = search_text(result)
            if error:
                text = "Search failed: " + text
            return text.replace(key, "[redacted]") if key else text
        except Exception:
            return "Search failed: Exa request failed."
    return execute


def search_text(result):
    if isinstance(result, str):
        # Codex wraps an MCP object with its script timing and output lines.
        start = result.find('{"content"')
        if start >= 0:
            try:
                result = json.JSONDecoder().raw_decode(result[start:])[0]
            except ValueError:
                pass
        else:
            try:
                result = json.loads(result)
            except ValueError:
                return result, False
    if isinstance(result, dict):
        text, error = search_text(result.get("content", ""))
        return text, error or bool(result.get("isError"))
    if isinstance(result, list):
        return "\n".join(item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
                         for item in result), False
    return str(result), False


def search_result_status(result):
    text, error = search_text(result)
    prefix = text[:300].lower()
    limited = any(marker in prefix for marker in ("exa's free mcp rate limit", "rate limit exceeded",
                                                   "rate_limit", "too many requests"))
    failed = error or limited or prefix.startswith(("error", "search failed"))
    return limited, failed


def valid_search_result(result):
    text, error = search_text(result)
    return not error and not search_result_status(result)[1] and all(
        re.search(pattern, text, re.MULTILINE) for pattern in
        (r"^Title: .+", r"^URL: https?://\S+", r"^(?:Highlights|Content|Text):"))
