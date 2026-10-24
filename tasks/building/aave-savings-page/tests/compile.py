import json
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion


@criterion
def compile_project(workspace: Path) -> dict:
    record = json.loads(Path("/logs/verifier/checks.json").read_text())["compile"]
    return {"score": record["passed"], "reasoning": record["reason"]}


rk.compile_project(name="compile")
