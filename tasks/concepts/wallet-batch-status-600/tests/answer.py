import sys
from pathlib import Path

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


@rk.criterion(description="The final reply is not empty")
def answered(workspace: Path) -> dict:
    if target_checks.final_reply(Path("/logs/agent/trajectory.json")).strip():
        return {"score": True, "reasoning": "There is a reply for the judge to grade."}
    return {"score": False, "reasoning": "The answer is empty."}


rk.answered(name="answered")
