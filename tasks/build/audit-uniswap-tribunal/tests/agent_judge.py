"""Prepare file inputs and a fresh user settings directory for an agent judge.

The audit variant also prepares the lookup judge's input: the agent's tool calls and their outputs, without its
messages or reasoning, written to /lookup/trajectory.txt.
"""
import os
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).parent))
from judge_credentials import credentials


def prepare(inputs, *, directory=Path("/judge"), home=Path("/root/judge-home")):
    inputs = [source for source in inputs if source.is_file()]
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    submission = directory / "submission"
    shutil.rmtree(submission, ignore_errors=True)
    submission.mkdir(mode=0o700)
    for source in inputs:
        shutil.copyfile(source, submission / source.name)
    output = Path(os.environ.get("REWARDKIT_LOG_DIR", "/logs/verifier"))
    snapshot = output / "judge-inputs"
    shutil.rmtree(snapshot, ignore_errors=True)
    shutil.copytree(submission, snapshot)
    (output / "judge-inputs.json").write_text(json.dumps({
        source.name: hashlib.sha256(source.read_bytes()).hexdigest() for source in inputs
    }, sort_keys=True) + "\n")
    shutil.rmtree(home, ignore_errors=True)
    (home / ".claude").mkdir(mode=0o700, parents=True)
    shutil.copyfile(str(Path(__file__).with_name("judge-settings.json")), home / ".claude/settings.json")
    prepare_lookup()
    return home


TRAJECTORY = Path("/logs/agent/trajectory.json")
LOOKUP = Path("/lookup")


def text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part["text"] if isinstance(part, dict) and isinstance(part.get("text"), str)
                         else "[image]" if isinstance(part, dict) and part.get("type") == "image"
                         else json.dumps(part, ensure_ascii=False) for part in value)
    return json.dumps(value, ensure_ascii=False)


def tool_record(trajectory, label="Agent") -> list[str]:
    """Keep every tool call and output, in embedded subagent trajectories too. Messages and reasoning are left out.

    An empty trajectory, a continuation in another file, or a subagent kept outside this file is incomplete evidence.
    """
    if not isinstance(trajectory, dict) or not isinstance(trajectory.get("steps"), list) or not trajectory["steps"]:
        raise ValueError(f"{label}: the trajectory has no steps")
    if trajectory.get("continued_trajectory_ref"):
        raise ValueError(f"{label}: the trajectory continues in another file")
    children = trajectory.get("subagent_trajectories") or []
    embedded = {child.get("trajectory_id") for child in children if isinstance(child, dict)}
    lines = [f"# {label}"]
    for step in trajectory["steps"]:
        if not isinstance(step, dict):
            raise ValueError(f"{label}: a step is not an object")
        calls = step.get("tool_calls") or []
        results = (step.get("observation") or {}).get("results") or []
        if not calls and not results:
            continue
        lines.append(f"## {label}, step {step.get('step_id')}")
        for call in calls:
            lines.append(f"Call {call.get('tool_call_id')}: {call.get('function_name')}")
            lines.append(json.dumps(call.get("arguments"), ensure_ascii=False))
        for result in results:
            for ref in result.get("subagent_trajectory_ref") or []:
                if ref.get("trajectory_path") or ref.get("trajectory_id") not in embedded:
                    raise ValueError(f"{label}: a subagent trajectory is not in this file")
            lines.append(f"Output of {result.get('source_call_id')}:")
            lines.append(text(result.get("content")))
        lines.append("")
    for child in children:
        lines.extend(tool_record(child, f"{label} > subagent {child.get('trajectory_id')}"))
    return lines


def prepare_lookup(source=TRAJECTORY, directory=LOOKUP, tests=Path(__file__).parent):
    """Write the lookup judge's only input. Without a readable trajectory the trial is an error, never a fail."""
    if not (tests / "lookup.toml").is_file():
        return
    output = Path(os.environ.get("REWARDKIT_LOG_DIR", "/logs/verifier"))
    try:
        record = "\n".join(tool_record(json.loads(source.read_text()))) + "\n"
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        output.mkdir(parents=True, exist_ok=True)
        for name in ("reward.json", "reward.txt"):
            (output / name).unlink(missing_ok=True)
        message = f"The lookup judge cannot read the trajectory {source}: {error}"
        (output / "judge-error.txt").write_text(message + "\n")
        raise SystemExit(message) from None
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(mode=0o700, parents=True)
    (directory / "trajectory.txt").write_text(record)
    # The replay compares this manifest, so a changed copy asks the lookup judge again.
    (output / "judge-inputs-lookup.json").write_text(json.dumps({
        "trajectory.txt": hashlib.sha256(record.encode()).hexdigest()}) + "\n")


def environment(home):
    names = {"PATH", "LANG", "PLAYWRIGHT_BROWSERS_PATH", "LD_LIBRARY_PATH", "FONTCONFIG_FILE",
             "REWARDKIT_JUDGE", "REWARDKIT_MODEL", "REWARDKIT_REASONING_EFFORT",
             "REWARDKIT_LOG_DIR", "REWARDKIT_FORCE_SUBSCRIPTION"}
    result = {name: value for name, value in os.environ.items()
              if name in names or name.startswith("ETHEVALS_REGRADE_")}
    result.update(HOME=str(home), PYTHON_DOTENV_DISABLED="1", DISABLE_AUTOUPDATER="1",
                  CLAUDE_CODE_DISABLE_BACKGROUND_TASKS="1")
    result["PATH"] = "/root/.local/bin:/usr/local/bin:" + result.get("PATH", "/usr/bin:/bin")
    result.update(credentials())
    return result


def run(inputs):
    home = prepare(inputs)
    binary = shutil.which("rewardkit")
    output = Path(os.environ.get("REWARDKIT_LOG_DIR", "/logs/verifier"))
    try:
        subprocess.run([binary, "/tests", "--yolo", "--max-concurrent-agent", "1"], env=environment(home), check=True)
        details = json.loads((output / "reward-details.json").read_text())

        def errors(value):
            if isinstance(value, dict):
                return bool(value.get("error")) or any(errors(child) for child in value.values())
            return isinstance(value, list) and any(errors(child) for child in value)

        if errors(details):
            raise RuntimeError("The judge failed. See reward-details.json.")
    except BaseException:
        (output / "reward.json").unlink(missing_ok=True)
        raise
    finally:
        projects = home / ".claude/projects"
        if projects.exists():
            shutil.copytree(projects, output / "judge-transcripts", dirs_exist_ok=True)


if __name__ == "__main__":
    run([Path(name) for name in sys.argv[1:]])
