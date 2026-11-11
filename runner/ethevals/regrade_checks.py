"""Replay RewardKit in a task image, with saved judge results when inputs match."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

sys.path.insert(0, "/opt")


def leaves(details):
    for detail in details.values():
        if detail.get("kind") == "group":
            yield from leaves({part["name"]: part["detail"] for part in detail["components"]})
        else:
            yield detail


def replay(tests_dir, *, workspace="/app", output="/logs/verifier/reward.json", **kwargs):
    from rewardkit import Reward
    from rewardkit.runner import _discover_layout, _evaluate_layout, _flatten_layout, _write_outputs

    item = json.loads(Path(os.environ["ETHEVALS_REGRADE_ITEM"]).read_text())
    source = Path(os.environ["ETHEVALS_REGRADE_SOURCE"])
    saved_path = source / "saved-verifier/reward-details.json"
    saved = list(leaves(json.loads(saved_path.read_text()))) if saved_path.exists() else []
    layout = _discover_layout(tests_dir, workspace)

    class SavedReward(Reward):
        def __init__(self, original, detail):
            self.name, self.reward_weight = original.name, original.reward_weight
            self.detail = detail

        @property
        def score(self):
            return self.detail["score"]

        def to_detail_dict(self, score):
            return self.detail

    cached = {}
    pending = []
    old_inputs = item["source_row"].get("checks_inputs", {})
    new_inputs = item["checks_inputs"]
    for reward in _flatten_layout(layout):
        if reward.judge is None:
            pending.append(reward)
            continue
        name = "tests/" + reward.name + ".toml"
        changed = old_inputs.get(name) != new_inputs.get(name) or old_inputs.get("@judge") != new_inputs.get("@judge")
        judge = reward.judge
        files = [*getattr(judge, "files", []), *([judge.atif_trajectory] if getattr(judge, "atif_trajectory", None) else [])]
        if getattr(judge, "agent", None):
            previous_inputs = source / "saved-verifier/judge-inputs.json"
            current_inputs = Path(os.environ.get("REWARDKIT_LOG_DIR", "/logs/verifier")) / "judge-inputs.json"
            if not previous_inputs.is_file() or not current_inputs.is_file() or previous_inputs.read_bytes() != current_inputs.read_bytes():
                changed = True
        for filename in files:
            previous = (source / "agent/trajectory.json" if filename == getattr(judge, "atif_trajectory", None) else
                        source / "saved-verifier" / Path(filename).relative_to("/logs/verifier"))
            if not previous.is_file() or previous.read_bytes() != Path(filename).read_bytes():
                changed = True
        if changed:
            if not item["judge_required"]:
                raise ValueError("The judge's input changed without a judge reserve")
            pending.append(reward)
        else:
            names = {criterion.name for criterion in reward.criteria}
            matching = [detail for detail in saved if detail.get("kind") in {"llm", "agent", "jev"}
                        and {criterion["name"] for criterion in detail["criteria"]} == names]
            if len(matching) != 1:
                raise ValueError("The saved judge result is unavailable")
            cached[id(reward)] = SavedReward(reward, matching[0])

    async def evaluate():
        for reward in pending:
            await reward.arun()
    asyncio.run(evaluate())

    def replace(node):
        if isinstance(node, Reward):
            return cached.get(id(node), node)
        node.inputs = {name: replace(child) for name, child in node.inputs.items()}
        return node
    layout.dimensions = {name: replace(node) for name, node in layout.dimensions.items()}
    if layout.spec_inputs is not None:
        layout.spec_inputs = {name: replace(node) for name, node in layout.spec_inputs.items()}
    rewards, details = _evaluate_layout(layout)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_outputs(destination, rewards, details)
    return rewards


def check_one():
    sys.path.insert(0, "/tests")
    item = json.loads(Path(os.environ["ETHEVALS_REGRADE_ITEM"]).read_text())
    if item["judge_required"] and Path("/tests/install_judge.py").is_file():
        from install_judge import install
        install()
    import rewardkit.runner
    rewardkit.runner.run = replay
    if Path("/tests/run_reward.py").is_file():
        sys.argv = ["/tests/run_reward.py"]
        runpy.run_path("/tests/run_reward.py", run_name="__main__")
    else:
        if not Path("/judge/submission").is_dir() and Path("/logs/verifier/judge-inputs").is_dir():
            from agent_judge import prepare, environment
            home = prepare(list(Path("/logs/verifier/judge-inputs").iterdir()))
            clean = environment(home)
            os.environ.clear()
            os.environ.update(clean)
        replay("/tests")


def batch():
    items = json.loads(Path("/batch/regrade.json").read_text())
    for index, item in enumerate(items):
        destination = Path("/batch") / str(index)
        if (destination / "regrade-finished.json").is_file():
            continue
        shutil.rmtree("/tests", ignore_errors=True)
        shutil.copytree("/original-tests", "/tests")
        shutil.rmtree("/logs", ignore_errors=True)
        shutil.rmtree("/judge", ignore_errors=True)
        shutil.copytree(destination / "agent", "/logs/agent")
        if (destination / "saved-verifier").is_dir():
            shutil.copytree(destination / "saved-verifier", "/logs/verifier")
        else:
            Path("/logs/verifier").mkdir(parents=True)
        for filename in ("reward.json", "reward-details.json"):
            (Path("/logs/verifier") / filename).unlink(missing_ok=True)
        (destination / "regrade-error.json").unlink(missing_ok=True)
        item_file = destination / "item.json"
        item_file.write_text(json.dumps(item))
        environment = {**os.environ, "ETHEVALS_REGRADE_ITEM": str(item_file), "ETHEVALS_REGRADE_SOURCE": str(destination),
                       "PYTHON_DOTENV_DISABLED": "1"}
        if item["kind"] == "concepts":
            wrapper = Path("/regrade-bin/rewardkit")
            wrapper.parent.mkdir(exist_ok=True)
            wrapper.write_text("#!/bin/sh\nexec python3 /regrade.py check\n")
            wrapper.chmod(0o755)
            environment["PATH"] = str(wrapper.parent) + ":" + os.environ["PATH"]
        if item["kind"] in {"concepts", "evidence"}:
            command = ["sh", "/tests/test.sh"]
        else:
            script = Path("/tests/test.sh").read_text()
            if "cp /opt/check_records.py /tests/check_records.py" in script:
                shutil.copyfile("/opt/check_records.py", "/tests/check_records.py")
            command = ["python3", "/regrade.py", "check"]
        completed = subprocess.run(command, env=environment, capture_output=True, text=True)
        Path("/logs/verifier/regrade.log").write_text(completed.stdout + completed.stderr)
        if completed.returncode:
            (destination / "regrade-error.json").write_text(json.dumps({
                "error_kind": "judge" if item["judge_required"] else "verification",
                "error_reason": "The regrade failed; see regrade.log."}))
        shutil.copytree("/logs/verifier", destination / "verifier", dirs_exist_ok=True)
        (destination / "regrade-finished.json").write_text(json.dumps(datetime.now(timezone.utc).isoformat()))


if __name__ == "__main__":
    batch() if sys.argv[1] == "batch" else check_one()
