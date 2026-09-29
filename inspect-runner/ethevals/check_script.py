"""Eval-owned scripts run inside the chain container, never on the host."""
import json
import re
from pathlib import PurePosixPath

from inspect_ai.util import sandbox
from inspect_ai.log import transcript
from inspect_ai.scorer import scorer, accuracy

from .sandboxes import runner_exec, scoring_exec, stop_agent
from .scoring_base import SubmissionFailed, checks_score, scoring_boundary

SETUP_TIMEOUT = 120
CHECK_SECONDS = 120


def validate_script(declaration, files):
    if declaration.type != "act" or declaration.modes != ["internet"]:
        raise ValueError("check_script requires an act eval with modes: [internet]")
    for path in ("scorer/check.py", "scorer/solution/run.sh"):
        if path not in files:
            raise ValueError(f"check_script requires {path}")


async def script_result(name, box=None):
    box = box if box is not None else sandbox("chain")
    exists = await runner_exec(box, ["/usr/bin/test", "-f", f"/eval/scorer/{name}.py"])
    if not exists.success:
        raise RuntimeError(f"Missing scorer script: {name}.py")
    execute = runner_exec if name == "setup" else scoring_exec
    result = await execute(box, ["/usr/bin/env", "RPC_URL=http://127.0.0.1:8546", "SOLC=/opt/solc",
        "/usr/bin/python3", f"/eval/scorer/{name}.py"], cwd="/eval",
        timeout=SETUP_TIMEOUT if name == "setup" else CHECK_SECONDS)
    if result.returncode < 0 or result.returncode >= 128:
        raise RuntimeError(f"{name}.py terminated with exit code {result.returncode}.")
    if not result.success:
        raise SubmissionFailed(f"{name}.py exited {result.returncode}: {result.stderr[-4096:]}")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise SubmissionFailed(f"Check script returned malformed JSON: {error}") from error


def setup_files(outputs, files):
    if not isinstance(outputs, dict) or set(outputs) != {"files"} or not isinstance(outputs["files"], dict):
        raise ValueError("setup.py must return a JSON object with a files mapping.")
    for name, text in outputs["files"].items():
        if not isinstance(name, str):
            raise ValueError("setup.py returned an invalid workspace file.")
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or str(path) != name or
                name in {"", "."} or not isinstance(text, str)):
            raise ValueError("setup.py returned an invalid workspace file.")
        if f"workspace/{name}" in files:
            raise ValueError(f"setup.py cannot replace workspace/{name}.")
    return outputs["files"]


async def setup_script(evaluation, environments):
    box = environments["chain"]
    for name, data in evaluation.files.items():
        if name.startswith("scorer/") and not name.startswith("scorer/solution/"):
            await box.write_file("/eval/" + name, data)
    if "scorer/setup.py" in evaluation.files:
        outputs = await script_result("setup", box)
        for name, text in setup_files(outputs, evaluation.files).items():
            for destination in ("default", "scorer"):
                await environments[destination].write_file("/workspace/" + name, text.encode())
    # The public proxy never exposes these controls. Enforce automining after setup.
    result = await runner_exec(box, ["/usr/bin/python3", "-c",
        "import sys; sys.path.insert(0, '/opt'); from rpc_filter import rpc; "
        "rpc('anvil_setIntervalMining', [0]); rpc('evm_setAutomine', [True])"], cwd="/eval")
    if not result.success:
        raise RuntimeError("Cannot configure chain mining after setup.")


async def run_solution(evaluation):
    box = sandbox("scorer")
    for name, data in evaluation.files.items():
        if name.startswith("workspace/"):
            await box.write_file("/" + name, data)
        if name.startswith("scorer/solution/"):
            await box.write_file("/workspace/" + name.removeprefix("scorer/solution/"), data)
    result = await runner_exec(box, ["/bin/bash", "/workspace/run.sh"], cwd="/workspace", timeout=120)
    if not result.success:
        raise ValueError(f"Reference solution exited {result.returncode}: {result.stderr[-4096:]}")


async def capture_chain():
    box = sandbox("chain")
    result = await runner_exec(box, ["/usr/bin/python3", "/opt/rpc_filter.py", "--freeze"], cwd="/eval", timeout=60)
    if not result.success:
        raise RuntimeError("Cannot close the chain for grading.")
    # Read bytes to retain the whole bounded log instead of Inspect's 20-line display.
    refusals = await box.read_file("/tmp/rpc-refusals.log", text=False)
    transcript().info({"rpc_refusals": refusals.decode("utf-8", errors="replace")})


def script_checks(value):
    if not isinstance(value, dict) or not value:
        raise ValueError("check.py must return a nonempty JSON object of named checks.")
    checks = {}
    for name, check in value.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) or not isinstance(check, dict) or
                set(check) != {"passed", "reason"} or type(check["passed"]) is not bool or
                not isinstance(check["reason"], str) or not check["reason"].strip()):
            raise ValueError("check.py requires stable names, boolean passed, and nonempty reason.")
        checks[f"script:{name}"] = {"passed": check["passed"], "reason": " ".join(check["reason"].split())}
    return checks


@scorer(metrics={"*": [accuracy()]})
def check_script_scorer(eval_id, eval_hash):
    async def score(state, target):
        await stop_agent()
        await capture_chain()
        value = await script_result("check")
        try:
            return checks_score(script_checks(value))
        except ValueError as error:
            raise SubmissionFailed(f"Check script failed: {error}") from error
    return scoring_boundary("script:check", score)
