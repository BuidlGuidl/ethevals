"""Discover reference checks before any player epoch, once per eval hash."""
import json
from dataclasses import replace

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import get_model
from inspect_ai.scorer import scorer, accuracy
from inspect_ai.solver import solver
from inspect_ai.util import SandboxEnvironmentSpec, sandbox

from .scorers import EVALUATIONS, checks_score, forge, forge_results, prepare_forge
from .sandboxes import compose_file, validate_compose

CHECK_SETS = {}


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
            raise RuntimeError(f"Reference tests failed: {result.stderr} {result.stdout}")
        return checks_score(checks)
    return score


def prepare_eval(evaluation, output, compose=None):
    if not any(item.kind == "tests" for item in evaluation.scorers):
        return evaluation
    path = output / "inputs" / evaluation.hash / "checks.json"
    if evaluation.test_checks:
        return evaluation
    if evaluation.hash in CHECK_SETS:
        names = CHECK_SETS[evaluation.hash]
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
        logs = eval(task, log_dir=str(path.parent / "preflight"), display="plain", retry_on_error=0, fail_on_error=False)
        log = logs[0]
        if log.error or not log.samples or log.samples[0].error:
            error = log.error or (log.samples[0].error if log.samples else None)
            raise ValueError(f"{evaluation.id}: reference check discovery failed: {error.message if error else 'no result'}")
        names = sorted(log.samples[0].scores["reference_checks"].metadata["checks"])
    CHECK_SETS[evaluation.hash] = names
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(names) + "\n")
    return replace(evaluation, test_checks=tuple(names))
