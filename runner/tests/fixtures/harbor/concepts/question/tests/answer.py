import json
from pathlib import Path

from rewardkit import criterion


@criterion
def unit(workspace: Path) -> dict:
    trajectory = Path("/logs/agent/trajectory.json")
    passed = trajectory.exists() and json.loads(trajectory.read_text())["steps"][-1]["message"] == "metre"
    return {"score": passed, "reasoning": "The final reply matches." if passed else "The final reply is absent or differs."}
