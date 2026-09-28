import io
import tarfile
from pathlib import Path, PurePosixPath

from inspect_ai.util import sandbox

from .config import read_yaml

IMAGES = Path(__file__).with_name("images")
MAX_WORKSPACE_BYTES = 50 * 1024 * 1024


def compose_file(folder: Path, eval_type: str) -> Path:
    own = folder / "compose.yaml"
    path = own if own.exists() else IMAGES / f"{eval_type}.compose.yaml"
    if not path.is_file():
        raise ValueError(f"{path}: no stock compose for type {eval_type!r}")
    validate_compose(path, stock=not own.exists())
    return path


def validate_compose(path: Path, *, stock: bool = False) -> None:
    data = read_yaml(path)

    def reject(message):
        raise ValueError(f"{path}: {message}")

    if "${" in path.read_text():
        reject("host environment substitution is forbidden")
    if set(data) - {"services", "networks", "volumes"}:
        reject("only services, networks, and named volumes are allowed")
    services, networks = data.get("services", {}), data.get("networks", {})
    if not isinstance(services, dict) or not {"default", "scorer"} <= services.keys():
        reject("services must include default and scorer")
    if networks != {"private": {"internal": True}, "internet": {}}:
        reject("networks must declare private with internal: true and internet: {}")
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
        if service.get("networks") != (["private", "internet"] if name in {"default", "scorer"} else ["private"]):
            reject(f"service {name}: only default and scorer can join internet; all services must join private")
        for volume in service.get("volumes", []):
            if name in {"default", "scorer"}:
                reject(f"service {name}: volumes are forbidden to keep agent and scorer files separate")
            if not isinstance(volume, dict) or volume.get("type") != "volume" or volume.get("source") not in volumes:
                reject(f"service {name}: host mounts are forbidden; use a declared named volume")
        if not isinstance(service.get("environment", {}), dict):
            reject(f"service {name}: environment must use explicit mapping values")
        if any(value is None for value in service.get("environment", {}).values()):
            reject(f"service {name}: inherited host environment is forbidden")


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


async def workspace_files() -> dict[str, bytes]:
    agent = sandbox("default")
    result = await agent.exec([
        "tar", "--exclude=out", "--exclude=cache", "--exclude=.git", "--exclude=node_modules",
        "-czf", "/tmp/ethevals-workspace.tar.gz", "-C", "/workspace", ".",
    ])
    if not result.success:
        raise RuntimeError(f"Cannot collect workspace: {result.stderr}")
    return unpack_workspace(await agent.read_file("/tmp/ethevals-workspace.tar.gz", text=False))
