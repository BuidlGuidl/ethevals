"""Discover reference checks for an eval and its scoring inputs."""
import hashlib
import json
from dataclasses import replace

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import get_model
from inspect_ai.scorer import scorer, accuracy
from inspect_ai.solver import solver
from inspect_ai.util import SandboxEnvironmentSpec, sandbox

from .scorers import EVALUATIONS, checks_score, forge, forge_results, prepare_forge, compiler_diagnostic
from .sandboxes import IMAGES, compose_file, validate_compose
from .config import read_yaml
from .images.tag import image_tag

CHECK_SETS = {}


def check_cache_path(evaluation, output, compose=None):
    image = read_yaml(compose or compose_file())["services"]["scorer"]["image"]
    inputs = [evaluation.hash.encode(), image.encode(), image_tag(IMAGES).encode(), b"forge-check-names-v1"]
    key = hashlib.sha256(b"\0".join(inputs)).hexdigest()
    return output / "inputs" / evaluation.hash / key / "checks.json"


def prepare_compose(evaluation, output):
    if "compose.yaml" not in evaluation.files:
        return compose_file()
    path = output.resolve() / "inputs" / evaluation.hash / "compose.yaml"
    normalized = validate_compose(path, data=evaluation.files["compose.yaml"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized)
    return path


@solver
def no_player():
    async def solve(state, generate):
        return state
    return solve


@scorer(metrics=[accuracy()])
def reference_checks(eval_id, eval_hash):
    evaluation = EVALUATIONS[(eval_id, eval_hash)]

    async def score(state, target):
        reference = {name.removeprefix("scorer/solution/"): data for name, data in evaluation.files.items()
                     if name.startswith("scorer/solution/")}
        box = sandbox("scorer")
        await prepare_forge(box, reference, evaluation.files)
        result = await forge(box)
        checks = {name: check for name, check in forge_results(result.stdout).items() if name.startswith("forge:test/")}
        if not result.success or not checks or not all(check["passed"] for check in checks.values()):
            failures = [f"{name}: {check['reason']}" for name, check in checks.items() if not check["passed"]]
            diagnostic = compiler_diagnostic(result.stdout, result.stderr)
            if diagnostic:
                failures.append(diagnostic)
            raise RuntimeError("Reference tests failed during check discovery. "
                               + ("; ".join(failures) or f"Forge exited {result.returncode} without test results."))
        return checks_score(checks)
    return score


def prepare_eval(evaluation, output, compose=None):
    if not any(item.kind == "tests" for item in evaluation.scorers):
        return evaluation
    path = check_cache_path(evaluation, output, compose)
    if evaluation.test_checks:
        return evaluation
    key = path.parent.name
    if key in CHECK_SETS:
        names = CHECK_SETS[key]
    elif path.exists():
        names = json.loads(path.read_text())
        if not isinstance(names, list) or not names or any(not isinstance(name, str) or not name.startswith("forge:test/") for name in names):
            raise ValueError(f"{path}: invalid reference check cache")
    else:
        EVALUATIONS[(evaluation.id, evaluation.hash)] = evaluation
        task = Task(name="reference-checks", dataset=[Sample(input="Discover reference checks.")],
                    solver=no_player(), scorer=reference_checks(evaluation.id, evaluation.hash),
                    model=get_model("mockllm/model"),
                    sandbox=SandboxEnvironmentSpec(type="docker", config=str(compose or prepare_compose(evaluation, output))))
        logs = eval(task, log_dir=str(path.parent / "preflight"), display="plain", retry_on_error=1, fail_on_error=False)
        log = logs[0]
        if log.error or not log.samples or log.samples[0].error:
            error = log.error or (log.samples[0].error if log.samples else None)
            raise ValueError(f"{evaluation.id}: reference check discovery failed: {error.message if error else 'no result'}")
        names = sorted(log.samples[0].scores["reference_checks"].metadata["checks"])
    CHECK_SETS[key] = names
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(names) + "\n")
    return replace(evaluation, test_checks=tuple(names))
