"""Let RewardKit finish the judge before resolving unfinished browser checks."""
import json
import os
from pathlib import Path
import sys

from rewardkit.runner import run


def judge_failed(value):
    if isinstance(value, dict):
        if value.get("kind") == "llm":
            return any(item["value"] == 0 and not item.get("error") for item in value.get("criteria", []))
        return any(judge_failed(child) for child in value.values())
    if isinstance(value, list):
        return any(judge_failed(child) for child in value)
    return False


def main():
    tests = Path(sys.argv[1] if len(sys.argv) > 1 else "/tests")
    output = Path(os.environ.get("REWARD_OUTPUT", "/logs/verifier/reward.json"))
    records = json.loads(Path(os.environ.get("CHECKS_FILE", "/logs/verifier/checks.json")).read_text())
    run(tests, workspace=os.environ.get("REWARD_WORKSPACE", "/workspace"), output=output)
    unresolved = [name for name in ["compile", "lists_every_proposal", "status_and_tallies_match",
        "quorum_counts_for_only", "end_moves_with_late_quorum", "wrap_then_delegate", "votes_at_snapshot",
        "canceled_status", "already_voted"] if name not in records or records[name].get("couldNotDrive")]
    details = json.loads(output.with_name("reward-details.json").read_text())
    known_failure = any(not record["passed"] and not record.get("couldNotDrive") for record in records.values())
    if unresolved and not known_failure and not judge_failed(details):
        output.unlink()
        raise RuntimeError("could not drive: " + ", ".join(unresolved))


if __name__ == "__main__":
    main()
