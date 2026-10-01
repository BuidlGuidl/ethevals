import io
import tarfile
import re
import os
from functools import wraps
import yaml
from pathlib import Path, PurePosixPath

from inspect_ai.util import sandbox

from .config import read_yaml
from .images.tag import image_tag
from .images.rpc_filter import redact
from .scoring_base import SubmissionFailed

IMAGES = Path(__file__).with_name("images")
MAX_WORKSPACE_BYTES = 50 * 1024 * 1024


def validate_compose(path: Path, *, data: bytes | None = None) -> bytes:
    data = read_yaml(path, data)

    def reject(message):
        raise ValueError(f"{path}: {message}")

    def check_interpolation(value):
        if type(value) not in {str, int, float, bool, type(None), dict, list}:
            reject("unsupported YAML scalar type")
        if isinstance(value, str) and re.search(r"\$(?:\{|[A-Za-z_])", value.replace("$$", "")):
            reject("host environment substitution is forbidden")
        if isinstance(value, dict):
            for key, child in value.items():
                check_interpolation(key)
                check_interpolation(child)
        elif isinstance(value, list):
            for child in value:
                check_interpolation(child)

    check_interpolation(data)
    if set(data) - {"services", "volumes"}:
        reject("only extra services and named volumes are allowed")
    services = data.get("services", {})
    if not isinstance(services, dict) or {"default", "scorer", "chain"} & services.keys():
        reject("default, scorer, and chain belong to the runner")
    volumes = data.get("volumes") or {}
    if not isinstance(volumes, dict):
        reject("volumes must be a mapping")
    for name, volume in volumes.items():
        if volume not in ({}, None):
            reject(f"volume {name}: host paths, external volumes, and driver options are forbidden")
    allowed = {"image", "init", "command", "entrypoint", "working_dir", "user", "environment",
               "networks", "volumes", "depends_on", "healthcheck", "mem_limit", "cpus"}
    for name, service in services.items():
        if not isinstance(service, dict):
            reject(f"service {name}: must be a mapping")
        extra = set(service) - allowed
        if extra:
            reject(f"service {name}: forbidden options {sorted(extra)}; privileged containers and host mounts are forbidden")
        if memory_bytes(service.get("mem_limit", 0)) <= 0:
            reject(f"service {name}: requires a positive mem_limit")
        if service.get("networks", ["work"]) != ["work"]:
            reject(f"service {name}: only the work network is allowed")
        service["networks"] = ["work"]
        for volume in service.get("volumes", []):
            if not isinstance(volume, dict) or volume.get("type") != "volume" or volume.get("source") not in volumes:
                reject(f"service {name}: host mounts are forbidden; use a declared named volume")
        if not isinstance(service.get("environment", {}), dict):
            reject(f"service {name}: environment must use explicit mapping values")
        if any(value is None for value in service.get("environment", {}).values()):
            reject(f"service {name}: inherited host environment is forbidden")
    return yaml.safe_dump(data, sort_keys=True).encode()


def memory_bytes(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([bkmg]?)b?", str(value).lower())
    if not match:
        raise ValueError(f"Invalid mem_limit: {value}")
    return int(float(match[1]) * {"": 1, "b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[match[2]])


def merged_compose(evaluation):
    document = read_yaml(IMAGES / ("chain.compose.yaml" if evaluation.declaration.chain else "stock.compose.yaml"))
    for name, service in document["services"].items():
        service["image"] = image_tag(IMAGES, "runner" if name == "default" else "chain")
        if name == "scorer":
            service["entrypoint"] = ["sleep", "infinity"]
            service["working_dir"] = "/workspace"
    if evaluation.fork:
        chain = document["services"]["chain"]
        chain["mem_limit"] = "1g"
        chain["environment"] = {
            "FORK_RPC_URL": "${" + evaluation.fork.rpc_variable + "}",
            "FORK_BLOCK_NUMBER": str(evaluation.fork.block),
        }
    if "compose.yaml" in evaluation.files:
        extra = yaml.safe_load(validate_compose(evaluation.folder / "compose.yaml", data=evaluation.files["compose.yaml"]))
        document["services"].update(extra.get("services", {}))
        document["volumes"] = extra.get("volumes", {})
    return document


def redact_exec(exec):
    @wraps(exec)
    async def redacted(*args, **kwargs):
        result = await exec(*args, **kwargs)
        urls = [os.environ.get(name) for name in ("MAINNET_RPC_URL", "BASE_RPC_URL")]
        result.stdout = redact(result.stdout, urls)
        result.stderr = redact(result.stderr, urls)
        return result
    return redacted


async def runner_exec(box, command, **kwargs):
    """Every privileged or scorer command starts with this owned environment."""
    return await redact_exec(box.exec)([
        "/usr/bin/env", "-i", "HOME=/home/agent", "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8", *command,
    ], **kwargs)


def unpack_workspace(data: bytes) -> dict[str, bytes]:
    files, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for item in archive:
            path = PurePosixPath(item.name)
            if path.is_absolute() or ".." in path.parts:
                raise SubmissionFailed("Workspace contains an unsafe path.")
            if item.isdir():
                continue
            if not item.isfile():
                raise SubmissionFailed(f"Workspace contains a link or special file: {item.name}")
            total += item.size
            if total > MAX_WORKSPACE_BYTES or len(files) >= 20000:
                raise SubmissionFailed("Workspace exceeds the 50 MiB or 20000 file limit.")
            files[str(path)] = archive.extractfile(item).read()
    return files


async def stop_agent():
    agent = sandbox("default")
    # Freeze every process owned by the unprivileged agent, including detached
    # writers. Root runs the collector; the agent cannot resume itself.
    stopped = await runner_exec(agent, ["/bin/sh", "-c", """
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    /usr/bin/pkill -STOP -u agent
    status=$?
    [ "$status" -le 1 ] || exit 125
    processes=$(/usr/bin/ps -u agent -o pid=,stat=) || exit 125
    printf '%s\n' "$processes" | /usr/bin/awk '$1 != 1 && $2 !~ /^[TtZ]/ {bad=1} END {exit bad}' && exit 0
    /usr/bin/sleep 0.05
done
exit 42
"""], user="root", cwd="/", timeout=10)
    if stopped.returncode == 42:
        raise SubmissionFailed("Agent processes kept escaping SIGSTOP.")
    if not stopped.success:
        raise RuntimeError(f"Cannot stop agent processes: {stopped.stderr}")


async def workspace_files() -> dict[str, bytes]:
    agent = sandbox("default")
    temporary = await runner_exec(agent, ["/usr/bin/mktemp", "-d", "/tmp/workspace.XXXXXXXXXX"], user="root", cwd="/")
    if not temporary.success:
        raise RuntimeError(f"Cannot allocate snapshot: {temporary.stderr}")
    path = temporary.stdout.strip() + "/workspace.tar.gz"
    result = await runner_exec(agent, ["/bin/bash", "-o", "pipefail", "-c", """
archive=$1
/usr/bin/find . \\( -name .git -o -name out -o -name cache \\) -prune -o -type f \\
    \\( ! -path '*/node_modules/*' -o -name '*.sol' \\) -print0 | \\
    /usr/bin/tar --null --no-recursion -T - -czf "$archive"
""", "snapshot", path], user="root", cwd="/workspace", timeout=60)
    if not result.success:
        raise RuntimeError(f"Cannot collect workspace: {result.stderr}")
    return unpack_workspace(await agent.read_file(path, text=False))
