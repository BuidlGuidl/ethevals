"""Eval-owned scripts run inside the chain container, never on the host."""
import json
import re
from pathlib import PurePosixPath
from typing import Literal

from inspect_ai.util import sandbox, OutputLimitExceededError

from .config import Declaration
from .sandboxes import runner_exec, stop_agent


class CheckScriptScorer(Declaration):
    kind: Literal["check_script"]


def validate_script(config, declaration, files):
    if declaration.type != "act" or declaration.modes != ["internet"]:
        raise ValueError("check_script requires an act eval with modes: [internet]")
    for path in ("scorer/check.py", "scorer/solution/run.sh"):
        if path not in files:
            raise ValueError(f"check_script requires {path}")
    if "workspace/chain.json" in files:
        raise ValueError("workspace/chain.json is reserved for setup output")


def script_cache_inputs(images):
    return [(images / name).read_bytes() for name in ("Chain.Dockerfile", "rpc_filter.py", "act.compose.yaml")] + [b"script-check-names-v1"]


async def script_result(name):
    box = sandbox("chain")
    result = await runner_exec(box, ["/bin/bash", "-c",
        '"$@" > >(/usr/bin/head -c 1048577 > /eval/script.stdout) '
        '2> >(/usr/bin/head -c 1048577 > /eval/script.stderr); result=$?; wait; exit "$result"',
        "script-output", "/usr/bin/env", "RPC_URL=http://127.0.0.1:8546", "SOLC=/opt/solc",
        "/usr/bin/python3", f"/eval/scorer/{name}.py"], cwd="/eval", timeout=120)
    stdout = await box.read_file("/eval/script.stdout", text=False)
    stderr = await box.read_file("/eval/script.stderr", text=False)
    if max(len(stdout), len(stderr)) > 1048576:
        raise OutputLimitExceededError("1 MiB", "")
    if not result.success:
        raise ValueError(f"{name}.py exited {result.returncode}.")
    return json.loads(stdout)


async def setup_script(config, evaluation, state):
    box = sandbox("chain")
    for name, data in evaluation.files.items():
        if name.startswith("scorer/") and not name.startswith("scorer/solution/"):
            await box.write_file("/eval/" + name, data)
    if "scorer/setup.py" in evaluation.files:
        outputs = await script_result("setup")
        if not isinstance(outputs, dict) or set(outputs) != {"files"} or not isinstance(outputs["files"], dict):
            raise ValueError("setup.py must return a JSON object with a files mapping.")
        for name, text in outputs["files"].items():
            path = PurePosixPath(name)
            if (path.is_absolute() or ".." in path.parts or str(path) != name or
                    not name or not isinstance(text, str)):
                raise ValueError("setup.py returned an invalid workspace file.")
            if f"workspace/{name}" in evaluation.files:
                raise ValueError(f"setup.py cannot replace workspace/{name}.")
            await sandbox("default").write_file("/workspace/" + name, text.encode())
    # The public proxy never exposes these controls. Enforce automining after setup.
    result = await runner_exec(box, ["/usr/bin/python3", "-c",
        "import sys; sys.path.insert(0, '/opt'); from rpc_filter import rpc; "
        "rpc('anvil_setIntervalMining', [0]); rpc('evm_setAutomine', [True])"], cwd="/eval")
    if not result.success:
        raise RuntimeError("Cannot configure chain mining after setup.")


async def run_solution(evaluation):
    box = sandbox("default")
    for name, data in evaluation.files.items():
        if name.startswith("scorer/solution/"):
            await box.write_file("/workspace/" + name.removeprefix("scorer/solution/"), data)
    result = await runner_exec(box, ["/bin/bash", "/workspace/run.sh"], cwd="/workspace", timeout=120)
    if not result.success:
        raise ValueError(f"Reference solution exited {result.returncode}: {result.stderr}")


async def capture_chain(config, evaluation, submission):
    if "chain" in submission.captures:
        return
    box = sandbox("chain")
    # The proxy drains accepted requests and closes ingress before stopping the agent.
    result = await runner_exec(box, ["/usr/bin/python3", "/opt/rpc_filter.py", "--freeze"], cwd="/eval", timeout=60)
    if not result.success:
        raise RuntimeError("Cannot close the chain for grading.")
    submission.captures["chain"] = json.loads(result.stdout)
    await stop_agent()
    # Public refusal reasons belong in the epoch log; script contents stay private.
    await runner_exec(box, ["/bin/cat", "/tmp/rpc-refusals.log"], cwd="/eval")


def script_checks(value):
    if not isinstance(value, dict) or not value:
        raise ValueError("check.py must return a nonempty JSON object of named checks.")
    checks = {}
    for name, check in value.items():
        if (not re.fullmatch(r"[a-z][a-z0-9_]*", name) or not isinstance(check, dict) or
                set(check) != {"passed", "reason"} or type(check["passed"]) is not bool or
                not isinstance(check["reason"], str) or not check["reason"].strip()):
            raise ValueError("check.py requires stable names, boolean passed, and nonempty reason.")
        checks[f"script:{name}"] = {"passed": check["passed"], "reason": " ".join(check["reason"].split())}
    return checks


async def discover_script(config, evaluation):
    from .scorers import Submission
    await run_solution(evaluation)
    await capture_chain(config, evaluation, Submission())
    return script_checks(await script_result("check"))


def check_script_scorer(config, evaluation):
    from .scorers import checks_score, failed_checks
    expected = evaluation.discovered_checks[config.kind]

    async def score(state, target, submission):
        try:
            checks = script_checks(await script_result("check"))
            missing = failed_checks(expected, "Check script did not report this check.")
            return checks_score({name: checks.get(name, missing[name]) for name in expected})
        except (ValueError, TimeoutError, OutputLimitExceededError) as error:
            return checks_score(failed_checks(expected, f"Check script failed: {error}"))
    return score
