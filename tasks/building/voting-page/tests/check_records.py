"""Expose each browser check as a named RewardKit criterion."""
import json
import os
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion

records = json.loads(Path(os.environ.get("CHECKS_FILE", "/logs/verifier/checks.json")).read_text())
has_failure = any(not record["passed"] and not record.get("couldNotDrive") for record in records.values())


@criterion(description="{check}")
def check_record(workspace: Path, check: str) -> dict:
    record = records.get(check, {"passed": False, "couldNotDrive": True, "reason": f"could not drive: no record for {check}"})
    judged = (Path(__file__).parent / "judge.toml").exists()
    if record.get("couldNotDrive") and not has_failure and not judged:
        raise RuntimeError(record["reason"])
    if type(record["passed"]) is not bool or not isinstance(record["reason"], str) or not record["reason"].strip():
        raise ValueError("Each check needs a boolean result and a reason.")
    return {"score": record["passed"], "reasoning": record["reason"]}


rk.check_record("compile", name="compile")
rk.check_record("lists_every_proposal", name="lists_every_proposal")
rk.check_record("status_and_tallies_match", name="status_and_tallies_match")
rk.check_record("quorum_counts_for_only", name="quorum_counts_for_only")
rk.check_record("end_moves_with_late_quorum", name="end_moves_with_late_quorum")
rk.check_record("wrap_then_delegate", name="wrap_then_delegate")
rk.check_record("votes_at_snapshot", name="votes_at_snapshot")
rk.check_record("canceled_status", name="canceled_status")
rk.check_record("already_voted", name="already_voted")
