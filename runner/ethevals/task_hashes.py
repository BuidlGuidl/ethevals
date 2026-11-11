"""Hash instructions, environments, and checks separately."""
import hashlib
import json
from pathlib import Path
import tomllib

from harbor.publisher.packager import DEFAULT_IGNORES
import pathspec


def digest(value) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def task_hashes(path: Path, judge: dict | None = None) -> dict:
    document = tomllib.loads((path / "task.toml").read_text())
    ignored = path / ".gitignore"
    spec = pathspec.PathSpec.from_lines("gitignore", ignored.read_text().splitlines() if ignored.exists() else DEFAULT_IGNORES)
    instruction, environment, checks = {}, {}, {}
    for file in sorted(path.rglob("*")):
        name = file.relative_to(path).as_posix()
        if not file.is_file() or spec.match_file(name) or name == "task.toml":
            continue
        if name == "README.md" or name.startswith("solution/"):
            continue
        inputs = instruction if name == "instruction.md" else checks if name.startswith("tests/") else environment
        inputs[name] = "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest()
    checks["@verifier"] = document.pop("verifier", {})
    checks["@artifacts"] = document.pop("artifacts", [])
    checks["@judge"] = judge
    document.pop("solution", None)
    info = document.get("task", {})
    for key in ("name", "description", "authors", "keywords", "version"):
        info.pop(key, None)
    if not info:
        document.pop("task", None)
    metadata = document.get("metadata", {})
    for key in ("pillar", "area", "layer", "modes"):
        metadata.pop(key, None)
    if not metadata:
        document.pop("metadata", None)
    environment["@settings"] = document
    return {"instruction_hash": digest(instruction), "environment_hash": digest(environment),
            "checks_hash": digest(checks), "checks_inputs": checks}
