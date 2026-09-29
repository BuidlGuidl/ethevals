"""Prepare containers and run setup before player epochs."""
import subprocess

import anyio
from inspect_ai.util import sandboxenv
from inspect_ai.util._sandbox.docker.docker import DockerSandboxEnvironment
import yaml

from .scorers import EVALUATIONS
from .check_script import setup_script
from .sandboxes import IMAGES, merged_compose, memory_bytes
from .images.tag import image_tag


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


def build_images():
    for image, dockerfile in (("runner", "Dockerfile"), ("chain", "Chain.Dockerfile")):
        docker_command(["docker", "build", "-f", str(IMAGES / dockerfile), "-t", image_tag(IMAGES, image), str(IMAGES)])


def prepare_compose(evaluation, output):
    document = merged_compose(evaluation)
    path = output.resolve() / "inputs" / evaluation.hash / "compose.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document))
    return path


def check_capacity(config, evaluations):
    memory = int(docker_command(["docker", "info", "--format", "{{.MemTotal}}"]).stdout)
    concurrency = config.concurrency
    per_epoch = max(sum(memory_bytes(service["mem_limit"]) for service in merged_compose(evaluation)["services"].values())
                    for evaluation in evaluations)
    if concurrency * per_epoch + 1024**3 > memory:
        raise ValueError(f"Docker memory must cover {per_epoch / 1024**3:g} GiB per concurrent epoch plus 1 GiB for the host. Reduce concurrency.")
