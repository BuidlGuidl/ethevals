"""Check the final ATIF reply with a task's answer rule."""
import json
from pathlib import Path
from typing import Callable

from rewardkit import criterion


def final_reply(trajectory: Path) -> str:
    if not trajectory.exists():
        return ""
    steps = json.loads(trajectory.read_text())["steps"]
    messages = [step for step in steps if step["source"] == "agent"]
    if not messages or messages[-1].get("tool_calls"):
        return ""
    message = messages[-1]["message"]
    return message if isinstance(message, str) else "\n".join(
        part["text"] for part in message if part["type"] == "text")


@criterion(shared=True)
def final_answer(workspace: Path, accepts: Callable[[str], bool],
                 trajectory: str = "/logs/agent/trajectory.json") -> dict:
    reply = final_reply(Path(trajectory))
    passed = bool(reply.strip()) and accepts(reply)
    reason = "Answer matches the target." if passed else "Answer does not match the target."
    if not reply.strip():
        reason = "The answer is empty."
    return {"score": passed, "reasoning": reason}
