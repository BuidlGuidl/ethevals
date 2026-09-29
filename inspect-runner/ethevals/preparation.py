"""Discover each scorer's reference checks before player epochs."""
import hashlib
import json
import subprocess
from dataclasses import replace

import anyio
from inspect_ai import Task, eval
from inspect_ai.model import get_model
from inspect_ai.scorer import scorer, accuracy
from inspect_ai.solver import solver
from inspect_ai.util import SandboxEnvironmentSpec, sandboxenv
from inspect_ai.util._sandbox.docker.docker import DockerSandboxEnvironment
import yaml

from .scorers import EVALUATIONS, SCORERS, checks_score
from .sandboxes import IMAGES, compose_file, validate_compose
from .config import read_yaml
from .images.tag import image_tag

CHECK_SETS = {}
DISCOVERY_SECONDS = 600


@sandboxenv(name="ethevals_docker")
class EvalDocker(DockerSandboxEnvironment):
    """Run scorer setup before Inspect starts sample time and cost limits."""

    @classmethod
    async def sample_init(cls, task_name, config, metadata):
        environments = await super().sample_init(task_name, config, metadata)
        try:
            evaluation = EVALUATIONS[(metadata["eval_id"], metadata["eval_hash"])]
            for item in evaluation.scorers:
                if setup := SCORERS[item.kind].setup:
                    await setup(item, evaluation, environments)
        except BaseException:
            with anyio.CancelScope(shield=True):
                await super().sample_cleanup(task_name, config, environments, False)
            raise
        return environments


def docker_command(command):
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Docker failed: {(error.stderr or error.stdout or str(error))[-8192:]}") from error


def check_cache_path(evaluation, output, compose=None):
    path = compose or compose_file(evaluation.declaration.type)
    images = {name: service["image"] for name, service in read_yaml(path)["services"].items()}
    inputs = [evaluation.hash.encode(),
              image_tag(IMAGES).encode(), (IMAGES / "foundry.toml").read_bytes(), b"scorer-discovery-v3"]
    if "chain" in images:
        inputs.append(image_tag(IMAGES, "chain").encode())
    for item in evaluation.scorers:
        inputs.extend(SCORERS[item.kind].cache_inputs(IMAGES))
    key = hashlib.sha256(b"\0".join(inputs)).hexdigest()
    return output / "inputs" / evaluation.hash / key / "checks.json"


def prepare_compose(evaluation, output):
    if "compose.yaml" not in evaluation.files:
        stock = compose_file(evaluation.declaration.type)
        document = yaml.safe_load(stock.read_bytes())
        for service in document["services"].values():
            service.pop("build", None)
        data = yaml.safe_dump(document).encode()
    else:
        data = evaluation.files["compose.yaml"]
    path = output.resolve() / "inputs" / evaluation.hash / "compose.yaml"
    normalized = validate_compose(path, data=data)
    images = {service["image"] for service in yaml.safe_load(normalized)["services"].values()}
    stock = compose_file("act")
    builders = [name for name, service in read_yaml(stock)["services"].items()
                if "build" in service and service["image"] in images]
    docker_command(["docker", "compose", "-f", str(stock), "build", *builders])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized)
    return path


def check_capacity(config):
    memory = int(docker_command(["docker", "info", "--format", "{{.MemTotal}}"]).stdout)
    concurrency = config.concurrency
    services = read_yaml(IMAGES / "act.compose.yaml")["services"]
    per_epoch = sum(int(service["mem_limit"][:-1]) * {"g": 1024**3, "m": 1024**2}[service["mem_limit"][-1]]
                    for service in services.values())
    if concurrency * per_epoch + 1024**3 > memory:
        raise ValueError(f"Docker memory must cover {per_epoch / 1024**3:g} GiB per concurrent epoch plus 1 GiB for the host. Reduce concurrency.")


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
        with anyio.fail_after(DISCOVERY_SECONDS):
            for item in evaluation.scorers:
                discover = SCORERS[item.kind].discover
                if discover:
                    found = await discover(item, evaluation)
                    if not found or not all(check["passed"] for check in found.values()):
                        reasons = "; ".join(f"{name}: {check['reason']}" for name, check in found.items() if not check["passed"])
                        raise RuntimeError(f"{item.kind}: reference checks failed during discovery: {reasons or 'no checks'}")
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
                    solver=no_player(),
                    scorer=reference_checks(evaluation.id, evaluation.hash), model=get_model("mockllm/model"),
                    sandbox=SandboxEnvironmentSpec(type="ethevals_docker", config=str(compose)))
        logs = eval(task, log_dir=str(path.parent / "preflight"), display="plain", retry_on_error=0, fail_on_error=False)
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
