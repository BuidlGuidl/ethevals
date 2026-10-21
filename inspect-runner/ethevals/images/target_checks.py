"""Check a final ATIF reply against a task's target data."""
import argparse
import json
from pathlib import Path
import string


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


def check_target(reply: str, settings: dict) -> dict:
    targets = settings["target"]
    targets = [targets] if isinstance(targets, str) else targets
    if not isinstance(targets, list) or not targets or any(
        not isinstance(target, str) or not target.strip() for target in targets
    ):
        raise ValueError("The target must be a nonempty string or list of nonempty strings.")
    location = settings.get("location", "exact")
    if location not in {"exact", "begin", "end", "any"}:
        raise ValueError("The target location must be exact, begin, end, or any.")
    answer = reply.strip(string.whitespace + string.punctuation)
    if settings.get("ignore_case", True):
        answer, targets = answer.casefold(), [target.casefold() for target in targets]
    passed = any({"exact": answer == target, "begin": answer.startswith(target),
                  "end": answer.endswith(target), "any": target in answer}[location] for target in targets)
    reason = "Answer matches the target." if passed else "Answer does not match the target."
    if not reply.strip():
        reason = "The answer is empty."
    return {"passed": passed, "reason": reason}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--trajectory", type=Path, default=Path("/logs/agent/trajectory.json"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier"))
    args = parser.parse_args()
    settings = json.loads(args.target.read_text())
    check = check_target(final_reply(args.trajectory), settings)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "checks.json").write_text(json.dumps({settings.get("name", "answer"): check}) + "\n")
    (args.output / "reward.txt").write_text(f"{int(check['passed'])}\n")
