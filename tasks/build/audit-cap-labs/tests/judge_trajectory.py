"""Copy the agent's tool calls and their outputs for the lookup judge, without its messages or reasoning."""
import json
import os
from pathlib import Path

SOURCE = Path("/logs/agent/trajectory.json")
TARGET = Path("/lookup/trajectory.txt")


def text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part["text"] if isinstance(part, dict) and isinstance(part.get("text"), str)
                         else f"[{part.get('type', 'part')}]" if isinstance(part, dict) else text(part)
                         for part in value)
    return json.dumps(value, ensure_ascii=False)


def tool_record(trajectory: dict) -> str:
    """Keep each step's tool calls and outputs. Messages and reasoning are left out."""
    lines = []
    for step in trajectory["steps"]:
        calls = step.get("tool_calls") or []
        results = (step.get("observation") or {}).get("results") or []
        if not calls and not results:
            continue
        lines.append(f"## Step {step.get('step_id')}")
        for call in calls:
            lines.append(f"Call {call.get('tool_call_id')}: {call.get('function_name')}")
            arguments = call.get("arguments")
            for name, value in (arguments.items() if isinstance(arguments, dict) else [("arguments", arguments)]):
                lines.append(f"{name}: {text(value)}")
        for result in results:
            lines.append(f"Output of {result.get('source_call_id')}:")
            lines.append(text(result.get("content")))
        lines.append("")
    return "\n".join(lines)


def main(source=SOURCE, target=TARGET, tests=Path(__file__).parent):
    # The free check removes judge files, and then no judge reads the copy.
    if not (tests / "lookup.toml").is_file():
        return
    try:
        record = tool_record(json.loads(source.read_text()))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        # No reward makes the trial an error, the same as a judge crash.
        output = Path(os.environ.get("REWARDKIT_LOG_DIR", "/logs/verifier"))
        output.mkdir(parents=True, exist_ok=True)
        for name in ("reward.json", "reward.txt"):
            (output / name).unlink(missing_ok=True)
        message = f"The lookup judge cannot read the trajectory {source}: {error}"
        (output / "judge-error.txt").write_text(message + "\n")
        raise SystemExit(message) from None
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.write_text(record)


if __name__ == "__main__":
    main()
