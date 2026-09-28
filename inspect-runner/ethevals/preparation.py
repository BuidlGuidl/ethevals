"""Discover each scorer's reference checks before player epochs."""
import hashlib
import json
import subprocess
from dataclasses import replace

from inspect_ai import Task, eval
from inspect_ai.model import get_model
from inspect_ai.scorer import scorer, accuracy
from inspect_ai.solver import solver
from inspect_ai.util import SandboxEnvironmentSpec
import yaml

from .scorers import EVALUATIONS, SCORERS, checks_score
from .sandboxes import IMAGES, compose_file, validate_compose

CHECK_SETS = {}


def check_cache_path(evaluation, output, compose=None):
    path = compose or compose_file(evaluation.declaration.type)
    inputs = [evaluation.hash.encode(), path.read_bytes(), b"scorer-discovery-v2"]
    for item in evaluation.scorers:
        inputs.extend(SCORERS[item.kind].cache_inputs(IMAGES))
    key = hashlib.sha256(b"\0".join(inputs)).hexdigest()
    return output / "inputs" / evaluation.hash / key / "checks.json"


def prepare_compose(evaluation, output):
    if "compose.yaml" not in evaluation.files:
        stock = compose_file(evaluation.declaration.type)
        document = yaml.safe_load(stock.read_bytes())
        built = {name: service for name, service in document["services"].items()
                 if name not in {"default", "scorer"} and "build" in service}
        if not built:
            return stock
        # Build shared service code, then execute its immutable local image ID.
        subprocess.run(["docker", "compose", "-f", str(stock), "build", *built], check=True,
                       capture_output=True)
        for service in built.values():
            result = subprocess.run(["docker", "image", "inspect", service["image"], "--format", "{{.Id}}"],
                                    check=True, capture_output=True, text=True)
            service["image"] = result.stdout.strip()
            del service["build"]
        # The agent image has its own build workflow and validator rules.
        for service in document["services"].values():
            service.pop("build", None)
        data = yaml.safe_dump(document).encode()
    else:
        data = evaluation.files["compose.yaml"]
    path = output.resolve() / "inputs" / evaluation.hash / "compose.yaml"
    normalized = validate_compose(path, data=data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized)
    return path


@solver
def initialize_scorers(evaluation):
    async def solve(state, generate):
        for item in evaluation.scorers:
            setup = SCORERS[item.kind].setup
            if setup:
                await setup(item, evaluation, state)
        return state
    return solve


@solver
def no_player():
    async def solve(state, generate):
        return state
    return solve


@scorer(metrics=[accuracy()])
def reference_checks(eval_id, eval_hash):
    evaluation = EVALUATIONS[(eval_id, eval_hash)]

    async def score(state, target):
        checks, discovered = {}, {}
        for item in evaluation.scorers:
            discover = SCORERS[item.kind].discover
            if discover:
                found = await discover(item, evaluation)
                if not found or not all(check["passed"] for check in found.values()):
                    raise RuntimeError(f"{item.kind}: reference checks failed during discovery")
                if checks.keys() & found.keys():
                    raise ValueError("Scorers returned duplicate check names")
                checks.update(found)
                discovered[item.kind] = sorted(found)
        result = checks_score(checks)
        result.metadata["discovered"] = discovered
        return result
    return score


def prepare_eval(evaluation, output, compose=None):
    required = {item.kind for item in evaluation.scorers if SCORERS[item.kind].discover}
    if required <= evaluation.discovered_checks.keys():
        return evaluation
    compose = compose or prepare_compose(evaluation, output)
    path = check_cache_path(evaluation, output, compose)
    key = path.parent.name
    if key in CHECK_SETS:
        names = CHECK_SETS[key]
    elif path.exists():
        names = json.loads(path.read_text())
    else:
        EVALUATIONS[(evaluation.id, evaluation.hash)] = evaluation
        task = Task(name="reference-checks", dataset=[evaluation.sample()],
                    setup=initialize_scorers(evaluation), solver=no_player(),
                    scorer=reference_checks(evaluation.id, evaluation.hash), model=get_model("mockllm/model"),
                    sandbox=SandboxEnvironmentSpec(type="docker", config=str(compose or prepare_compose(evaluation, output))))
        logs = eval(task, log_dir=str(path.parent / "preflight"), display="plain", retry_on_error=1, fail_on_error=False)
        log = logs[0]
        if log.error or not log.samples or log.samples[0].error:
            error = log.error or (log.samples[0].error if log.samples else None)
            raise ValueError(f"{evaluation.id}: reference check discovery failed: {error.message if error else 'no result'}")
        names = log.samples[0].scores["reference_checks"].metadata["discovered"]
    if (not isinstance(names, dict) or set(names) != required or
            any(not isinstance(group, list) or not group or
                any(not isinstance(name, str) or not name.strip() for name in group) or
                len(set(group)) != len(group) for group in names.values())):
        raise ValueError(f"{path}: invalid reference check cache")
    CHECK_SETS[key] = names
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(names) + "\n")
    return replace(evaluation, discovered_checks={kind: tuple(group) for kind, group in names.items()})
