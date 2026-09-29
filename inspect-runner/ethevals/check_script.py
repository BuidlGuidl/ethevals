"""Eval-owned scripts run inside the chain container, never on the host."""
import json
import re
from pathlib import PurePosixPath
from typing import Literal

from inspect_ai.util import sandbox
from inspect_ai.log import transcript

from .config import Declaration
from .sandboxes import runner_exec, scoring_exec
from .scoring_base import Submission, SubmissionFailed, checks_score, failed_checks

SETUP_TIMEOUT = 120
CHECK_SECONDS = 120


class CheckScriptScorer(Declaration):
    kind: Literal["check_script"]


def validate_script(config, declaration, files):
    if declaration.type != "act" or declaration.modes != ["internet"]:
        raise ValueError("check_script requires an act eval with modes: [internet]")
    script_path(files, "check", required=True)
    script_path(files, "setup")


def script_path(files, name, *, required=False):
    paths = [path for path in files if PurePosixPath(path).parent == PurePosixPath("scorer")
             and (PurePosixPath(path).name == name or PurePosixPath(path).name.startswith(name + "."))]
    if len(paths) > 1 or (required and not paths):
        raise ValueError(f"Expected one scorer/{name} or scorer/{name}.<ext> file")
    return paths[0] if paths else None


def script_cache_inputs(images):
    return [b"script-check-names-v1"]


async def script_result(name, box=None):
    box = box if box is not None else sandbox("chain")
    found = await runner_exec(box, ["/usr/bin/find", "/eval/scorer", "-maxdepth", "1", "-type", "f"])
    path = script_path([p.removeprefix("/eval/") for p in found.stdout.splitlines()], name, required=True)
    executable = "/eval/" + path
    await runner_exec(box, ["/bin/chmod", "+x", executable])
    execute = runner_exec if name == "setup" else scoring_exec
    result = await execute(box, ["/bin/bash", "-c",
        '/bin/rm -f /eval/script.status /eval/script.stdout.pipe /eval/script.stderr.pipe || exit 125; '
        '/usr/bin/mkfifo /eval/script.stdout.pipe /eval/script.stderr.pipe || exit 125; '
        '{ /usr/bin/head -c 1048577 > /eval/script.stdout; status=$?; /bin/cat > /dev/null; exit "$status"; } < /eval/script.stdout.pipe & out=$!; '
        '{ /usr/bin/head -c 1048577 > /eval/script.stderr; status=$?; /bin/cat > /dev/null; exit "$status"; } < /eval/script.stderr.pipe & err=$!; '
        '"$@" > /eval/script.stdout.pipe 2> /eval/script.stderr.pipe; result=$?; '
        'printf "%s" "$result" > /eval/script.status || exit 125; '
        'wait "$out"; out_status=$?; wait "$err"; err_status=$?; '
        'if (( out_status || err_status )); then exit 125; fi; '
        '/bin/rm -f /eval/script.stdout.pipe /eval/script.stderr.pipe || exit 125; '
        'if (( result == 125 )); then exit 1; fi; exit "$result"',
        "script-output", "/usr/bin/env", "RPC_URL=http://127.0.0.1:8546", "PUBLIC_RPC_URL=http://chain:8545",
        "SOLC=/opt/solc", "FOUNDRY_OFFLINE=true", executable], cwd="/eval",
        timeout=SETUP_TIMEOUT if name == "setup" else CHECK_SECONDS)
    if result.returncode == 125:
        raise RuntimeError("Cannot capture check script output.")
    if not result.success:
        try:
            status = int(await box.read_file("/eval/script.status"))
        except FileNotFoundError as error:
            raise RuntimeError(f"{path} wrapper exited {result.returncode} without a script status.") from error
        if status == 0:
            raise RuntimeError(f"{path} wrapper exited {result.returncode} after a successful script.")
    stdout = await box.read_file("/eval/script.stdout", text=False)
    stderr = await box.read_file("/eval/script.stderr", text=False)
    if max(len(stdout), len(stderr)) > 1048576:
        raise SubmissionFailed("Check script exceeded its 1 MiB output limit.")
    if not result.success:
        raise RuntimeError(f"{path} exited {status}: {stderr[-4096:].decode('utf-8', errors='replace')}")
    try:
        return json.loads(stdout)
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


async def setup_script(config, evaluation, environments):
    box = environments["chain"]
    for name, data in evaluation.files.items():
        if name.startswith("scorer/") and not name.startswith("scorer/solution/"):
            await box.write_file("/eval/" + name, data)
    if script_path(evaluation.files, "setup"):
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


async def run_solution(evaluation, box=None):
    box = box if box is not None else sandbox("scorer")
    files = {name.removeprefix("workspace/"): data for name, data in evaluation.files.items() if name.startswith("workspace/")}
    files.update({name.removeprefix("scorer/solution/"): data for name, data in evaluation.files.items()
                  if name.startswith("scorer/solution/")})
    for name, data in files.items():
        await box.write_file("/workspace/" + name, data)
    if "scorer/solution/run.sh" in evaluation.files:
        result = await runner_exec(box, ["/bin/bash", "/workspace/run.sh"], cwd="/workspace", timeout=120)
        if not result.success:
            raise ValueError(f"Reference solution exited {result.returncode}: {result.stderr[-4096:]}")


async def capture_chain(config, evaluation, submission):
    box = sandbox("chain")
    # Anvil returns transaction hashes before mining finishes. Stop future mining
    # and wait for its mining mutex before the check reads state.
    result = await runner_exec(box, ["/bin/bash", "-ec",
        "cast rpc --rpc-url http://127.0.0.1:8546 evm_setAutomine false; "
        "cast rpc --rpc-url http://127.0.0.1:8546 evm_mine"], timeout=60)
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


async def discover_script(config, evaluation):
    await run_solution(evaluation)
    await capture_chain(config, evaluation, Submission())
    return script_checks(await script_result("check"))


def check_script_scorer(config, evaluation):
    expected = evaluation.discovered_checks[config.kind]

    async def score(state, target, submission):
        value = await script_result("check")
        checks = script_checks(value)
        missing = failed_checks(expected, "Check script did not report this check.")
        return checks_score({name: checks.get(name, missing[name]) for name in expected})
    return score
