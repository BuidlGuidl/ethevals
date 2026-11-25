"""Recognize a refusal or an empty Concepts reply in saved work."""
import json
from pathlib import Path

from .images.target_checks import final_reply


def blocked_by_provider(message: str) -> bool:
    """OpenCode reports a provider's safety block as an error event; Harbor reads it as an API error."""
    for line in message.splitlines():
        try:
            event = json.JSONDecoder().raw_decode(line, line.index("{"))[0]
            if event["type"] == "error" and json.loads(event["error"]["data"]["message"])["metadata"]["error_type"] == "content_policy_violation":
                return True
        except (ValueError, KeyError, TypeError):
            continue
    return False


def no_answer(folder: Path, task_id: str, exception: str | None) -> dict | None:
    provider = folder / "agent/provider.json"
    stop = json.loads(provider.read_text()) if provider.is_file() else {}
    # Harbor skips the checks after a safety refusal, so any text the agent left is never checked.
    if exception == "AgentSafetyRefusalError":
        return {"kind": "refused", "stop_reason": stop.get("stop_reason") or exception}
    trajectory = folder / "agent/trajectory.json"
    if trajectory.is_file() and final_reply(trajectory).strip():
        return None
    if stop.get("refused"):
        return {"kind": "refused", "stop_reason": stop.get("stop_reason") or exception}
    if exception is None and task_id.startswith("concepts/"):
        return {"kind": "empty", "stop_reason": stop.get("stop_reason")}
    return None
