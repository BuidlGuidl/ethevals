from pathlib import Path

import rewardkit as rk

REPORT = Path("/logs/verifier/findings.md")
MISSING = "No findings.md was written."


@rk.criterion(description="The agent wrote a findings.md report")
def report_written(workspace: Path) -> dict:
    text = REPORT.read_text(errors="replace").strip() if REPORT.exists() else ""
    if text and text != MISSING:
        return {"score": True, "reasoning": "There is a report for the judge to read."}
    return {"score": False, "reasoning": "No findings.md was written, or it is empty."}


rk.report_written(name="report_written")
