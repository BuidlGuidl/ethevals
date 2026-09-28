import io
import json
import tarfile
import re
import yaml
from pathlib import Path, PurePosixPath

from inspect_ai.util import sandbox

from .config import read_yaml
from .images.tag import image_tag

IMAGES = Path(__file__).with_name("images")
SOLC_VERSIONS = (json.loads((IMAGES / "solc.json").read_bytes())["version"],)
MAX_WORKSPACE_BYTES = 50 * 1024 * 1024


def compose_file(eval_type=None) -> Path:
    path = IMAGES / ("act.compose.yaml" if eval_type == "act" else "stock.compose.yaml")
    validate_compose(path, stock=True)
    return path


def validate_compose(path: Path, *, stock: bool = False, data: bytes | None = None) -> bytes:
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
    if set(data) - {"services", "networks", "volumes"}:
        reject("only services, networks, and named volumes are allowed")
    services, networks = data.get("services", {}), data.get("networks", {})
    if not isinstance(services, dict) or not {"default", "scorer"} <= services.keys():
        reject("services must include default and scorer")
    if networks != {"private": {"internal": True, "driver_opts": {
            "com.docker.network.bridge.inhibit_ipv4": "true"}}, "internet": {}}:
        reject("networks must declare private with internal: true and inhibit_ipv4: 'true', and internet: {}")
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
        extra = set(service) - allowed - ({"build"} if stock else set())
        if extra:
            reject(f"service {name}: forbidden options {sorted(extra)}; privileged containers and host mounts are forbidden")
        if name in {"default", "scorer"}:
            runner_image = image_tag(IMAGES)
            if service.get("image") != runner_image or service.get("user", "agent") != "agent":
                reject(f"service {name}: requires the runner image and the agent user; expected {runner_image}")
        if name == "chain" and service.get("image") != image_tag(IMAGES, "chain"):
            reject(f"service chain: requires the chain image {image_tag(IMAGES, 'chain')}")
        if service.get("networks") != (["private", "internet"] if name == "default" else ["private"]):
            reject(f"service {name}: only default can join internet; all services must join private")
        for volume in service.get("volumes", []):
            if name in {"default", "scorer"}:
                reject(f"service {name}: volumes are forbidden to keep agent and scorer files separate")
            if not isinstance(volume, dict) or volume.get("type") != "volume" or volume.get("source") not in volumes:
                reject(f"service {name}: host mounts are forbidden; use a declared named volume")
        if not isinstance(service.get("environment", {}), dict):
            reject(f"service {name}: environment must use explicit mapping values")
        if any(value is None for value in service.get("environment", {}).values()):
            reject(f"service {name}: inherited host environment is forbidden")
        if name in {"default", "scorer"} and any(
            key.startswith("LD_") or key in {"BASH_ENV", "ENV", "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS"}
            for key in service.get("environment", {})
        ):
            reject(f"service {name}: loader and shell startup environment overrides are forbidden")
    return yaml.safe_dump(data, sort_keys=True).encode()


async def runner_exec(box, command, **kwargs):
    """Every privileged or scorer command starts with this owned environment."""
    return await box.exec([
        "/usr/bin/env", "-i", "HOME=/home/agent", "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8", *command,
    ], **kwargs)


def unpack_workspace(data: bytes) -> dict[str, bytes]:
    files, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for item in archive:
            path = PurePosixPath(item.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Workspace contains an unsafe path.")
            if item.isdir():
                continue
            if not item.isfile():
                raise ValueError(f"Workspace contains a link or special file: {item.name}")
            total += item.size
            if total > MAX_WORKSPACE_BYTES or len(files) >= 20000:
                raise ValueError("Workspace exceeds the 50 MiB or 20000 file limit.")
            files[str(path)] = archive.extractfile(item).read()
    return files


async def stop_agent():
    agent = sandbox("default")
    # Freeze every process owned by the unprivileged agent, including detached
    # writers. Root runs the collector; the agent cannot resume itself.
    stopped = await runner_exec(agent, ["/bin/sh", "-c", """
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    /usr/bin/pkill -STOP -u agent
    /usr/bin/ps -u agent -o pid=,stat= | /usr/bin/awk '$1 != 1 && $2 !~ /^[TtZ]/ {bad=1} END {exit bad}' && exit 0
    /usr/bin/sleep 0.05
done
exit 1
"""], user="root", cwd="/", timeout=10)
    if not stopped.success:
        raise ValueError(f"Cannot stop agent processes: {stopped.stderr}")


async def workspace_files() -> dict[str, bytes]:
    agent = sandbox("default")
    temporary = await runner_exec(agent, ["/usr/bin/mktemp", "-d", "/tmp/ethevals.XXXXXXXXXX"], user="root", cwd="/")
    if not temporary.success:
        raise RuntimeError(f"Cannot allocate snapshot: {temporary.stderr}")
    path = temporary.stdout.strip() + "/workspace.tar.gz"
    result = await runner_exec(agent, ["/bin/sh", "-c", """
archive=$1
set --
for tree in src lib; do
    if [ -e "$tree" ] || [ -L "$tree" ]; then set -- "$@" "$tree"; fi
done
/usr/bin/tar --anchored --exclude=lib/openzeppelin-contracts --exclude=lib/forge-std \
    -czf "$archive" --files-from /dev/null "$@"
""", "snapshot", path], user="root", cwd="/workspace", timeout=60)
    if not result.success:
        raise ValueError(f"Cannot collect workspace: {result.stderr}")
    return unpack_workspace(await agent.read_file(path, text=False))
