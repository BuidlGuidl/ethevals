"""Prepare containers and run setup before player epochs."""
import subprocess

import anyio
from inspect_ai.util import sandboxenv
from inspect_ai.util._sandbox.docker.docker import DockerSandboxEnvironment
import yaml

from .scorers import EVALUATIONS
from .check_script import setup_script
from .sandboxes import IMAGES, compose_file, validate_compose
from .config import read_yaml


@sandboxenv(name="ethevals_docker")
class EvalDocker(DockerSandboxEnvironment):
    """Run scorer setup before Inspect starts sample time and cost limits."""

    @classmethod
    async def sample_init(cls, task_name, config, metadata):
        environments = await super().sample_init(task_name, config, metadata)
        try:
            evaluation = EVALUATIONS[(metadata["eval_id"], metadata["eval_hash"])]
            if "check_script" in evaluation.scorer_kinds:
                await setup_script(evaluation, environments)
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
