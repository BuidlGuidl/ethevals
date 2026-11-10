"""Recognize a refusal or an empty Concepts reply in saved work."""
import json
from pathlib import Path

from .images.target_checks import final_reply


def no_answer(folder: Path, task_id: str, exception: str | None) -> dict | None:
    trajectory = folder / "agent/trajectory.json"
    if trajectory.is_file() and final_reply(trajectory).strip():
        return None
    provider = folder / "agent/provider.json"
    stop = json.loads(provider.read_text()) if provider.is_file() else {}
    if exception == "AgentSafetyRefusalError" or stop.get("refused"):
        return {"kind": "refused", "stop_reason": stop.get("stop_reason") or exception}
    if exception is None and task_id.startswith("concepts/"):
        return {"kind": "empty", "stop_reason": stop.get("stop_reason")}
    return None
