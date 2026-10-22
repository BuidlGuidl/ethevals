"""Turn test-tool records into named RewardKit criteria."""
import json
import os
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion


records = json.loads(Path(os.environ.get("CHECKS_FILE", "/logs/verifier/checks.json")).read_text())
if not isinstance(records, dict) or not records:
    raise ValueError("Test tools must write at least one check record.")


@criterion(description="{check}")
def check_record(workspace: Path, check: str) -> dict:
    record = records[check]
    return {"score": record["passed"], "reasoning": record["reason"]}


for name, record in records.items():
    if (not name.strip() or not isinstance(record, dict)
            or type(record.get("passed")) is not bool or not isinstance(record.get("reason"), str)
            or not record["reason"].strip() or len(record["reason"].splitlines()) != 1):
        raise ValueError("Each check needs a name, boolean passed, and one-line reason.")
    rk.check_record(name, name=name)
