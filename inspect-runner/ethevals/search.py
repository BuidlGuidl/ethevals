"""Read Exa results from native MCP and Codex code-mode transcripts."""
import json
import re


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
