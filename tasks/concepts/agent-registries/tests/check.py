"""Check the final reply from Harbor's ATIF trajectory."""
import json
from pathlib import Path
import string


trajectory = Path("/logs/agent/trajectory.json")
reply = ""
if trajectory.exists():
    steps = json.loads(trajectory.read_text())["steps"]
    messages = [step for step in steps if step["source"] == "agent"]
    if messages and not messages[-1].get("tool_calls"):
        message = messages[-1]["message"]
        reply = message if isinstance(message, str) else "\n".join(
            part["text"] for part in message if part["type"] == "text"
        )

passed = reply.strip(string.whitespace + string.punctuation).endswith("8004")
reason = "Answer matches the target." if passed else "Answer does not match the target."
if not reply.strip():
    reason = "The answer is empty."
output = Path("/logs/verifier")
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({
    "erc_number": {"passed": passed, "reason": reason},
}) + "\n")
(output / "reward.txt").write_text("1\n" if passed else "0\n")
