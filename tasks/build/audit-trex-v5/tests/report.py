from pathlib import Path

import rewardkit as rk

REPORT = Path("/logs/verifier/findings.md")


@rk.criterion(description="The agent wrote a findings report")
def report_written(workspace: Path) -> dict:
    if REPORT.is_file() and REPORT.read_text(errors="replace").strip():
        return {"score": True, "reasoning": "There is a report for the judge to read."}
    return {"score": False, "reasoning": "/workspace/findings.md is missing or empty."}


rk.report_written(name="report_written")
