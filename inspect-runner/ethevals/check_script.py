"""Eval-owned scripts run inside the chain container, never on the host."""
import json
import re
from pathlib import PurePosixPath

from inspect_ai.util import sandbox
from inspect_ai.log import transcript
from inspect_ai.scorer import scorer, accuracy

from .sandboxes import runner_exec, scoring_exec, stop_agent
from .scoring_base import checks_score, scoring_boundary
from .config import uses_sandbox

SETUP_TIMEOUT = 120
CHECK_SECONDS = 120


def validate_script(declaration, files):
    if not declaration.chain or not all(uses_sandbox(mode) for mode in declaration.modes):
        raise ValueError("check_script requires a chain and agent modes only")
    script_path(files, "check", required=True)
    script_path(files, "setup")


def script_path(files, name, *, required=False):
    directory = "setup" if name == "setup" else "scorer"
    paths = [path for path in files if PurePosixPath(path).parent == PurePosixPath(directory)
             and (PurePosixPath(path).name == name or PurePosixPath(path).name.startswith(name + "."))]
    if len(paths) > 1 or (required and not paths):
        raise ValueError(f"Expected one {directory}/{name} or {directory}/{name}.<ext> file")
    return paths[0] if paths else None


async def script_result(path, box=None):
    box = box if box is not None else sandbox("chain")
    setup = PurePosixPath(path).name.split(".")[0] == "setup"
    execute = runner_exec if setup else scoring_exec
    result = await execute(box, ["/usr/bin/env", "RPC_URL=http://127.0.0.1:8546", "PUBLIC_RPC_URL=http://chain:8545",
        "SOLC=/opt/solc", "FOUNDRY_OFFLINE=true", "/eval/" + path], cwd="/eval",
        timeout=SETUP_TIMEOUT if setup else CHECK_SECONDS)
    if not result.success:
        raise RuntimeError(f"{path} exited {result.returncode}: {result.stderr[-4096:]}")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise ValueError(f"Check script returned malformed JSON: {error}") from error


def setup_files(outputs, files):
    if not isinstance(outputs, dict) or set(outputs) != {"files"} or not isinstance(outputs["files"], dict):
        raise ValueError("Setup script must return a JSON object with a files mapping.")
    for name, text in outputs["files"].items():
        if not isinstance(name, str):
            raise ValueError("Setup script returned an invalid workspace file.")
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or str(path) != name or
                name in {"", "."} or not isinstance(text, str)):
            raise ValueError("Setup script returned an invalid workspace file.")
        if f"workspace/{name}" in files:
            raise ValueError(f"Setup script cannot replace workspace/{name}.")
    return outputs["files"]


async def setup_script(evaluation, environments):
    box = environments["chain"]
    for name, data in evaluation.files.items():
        if name.startswith(("scorer/", "setup/")):
            await box.write_file("/eval/" + name, data)
    scripts = [script_path(evaluation.files, name) for name in ("setup", "check")]
    await runner_exec(box, ["/bin/chmod", "+x", *("/eval/" + path for path in scripts if path)])
    if path := scripts[0]:
        outputs = await script_result(path, box)
        for name, text in setup_files(outputs, evaluation.files).items():
            for destination in ("default", "scorer"):
                await environments[destination].write_file("/workspace/" + name, text.encode())
    # The public proxy never exposes these controls. Enforce automining after setup.
    result = await runner_exec(box, ["/usr/bin/python3", "-c",
        "import sys; sys.path.insert(0, '/opt'); from rpc_filter import rpc; "
        "rpc('anvil_setIntervalMining', [0]); rpc('evm_setAutomine', [True])"], cwd="/eval", timeout=60)
    if not result.success:
        raise RuntimeError("Cannot configure chain mining after setup.")


async def run_solution(evaluation, box=None):
    box = box if box is not None else sandbox("scorer")
    files = {name.removeprefix("workspace/"): data for name, data in evaluation.files.items() if name.startswith("workspace/")}
    files.update({name.removeprefix("solution/"): data for name, data in evaluation.files.items()
                  if name.startswith("solution/")})
    for name, data in files.items():
        await box.write_file("/workspace/" + name, data)
    if "solution/run.sh" in evaluation.files:
        result = await runner_exec(box, ["/bin/bash", "/workspace/run.sh"], cwd="/workspace", timeout=120)
        if not result.success:
            raise ValueError(f"Reference solution exited {result.returncode}: {result.stderr[-4096:]}")


async def capture_chain():
    box = sandbox("chain")
    # Wait for Anvil's mining mutex before the check reads state.
    result = await runner_exec(box, ["cast", "rpc", "--rpc-url", "http://127.0.0.1:8546", "evm_mine"], timeout=60)
    if not result.success:
        raise RuntimeError(f"Cannot settle chain mining: {result.stderr}")
    # Read bytes instead of Inspect's 20-line display.
    refusals = await box.read_file("/tmp/rpc-refusals.log", text=False)
    transcript().info({"rpc_refusals": refusals.decode("utf-8", errors="replace")})


def script_checks(value):
    if not isinstance(value, dict) or not value:
        raise ValueError("Check script must return a nonempty JSON object of named checks.")
    checks = {}
    for name, check in value.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) or not isinstance(check, dict) or
                set(check) != {"passed", "reason"} or type(check["passed"]) is not bool or
                not isinstance(check["reason"], str) or not check["reason"].strip()):
            raise ValueError("Check script requires stable names, boolean passed, and nonempty reason.")
        checks[f"script:{name}"] = {"passed": check["passed"], "reason": " ".join(check["reason"].split())}
    return checks


@scorer(metrics={"*": [accuracy()]})
def check_script_scorer(eval_id, eval_hash):
    from .scorers import EVALUATIONS
    evaluation = EVALUATIONS[(eval_id, eval_hash)]

    async def score(state, target):
        await stop_agent()
        await capture_chain()
        value = await script_result(script_path(evaluation.files, "check", required=True))
        return checks_score(script_checks(value))
    return scoring_boundary("script:check", score)
