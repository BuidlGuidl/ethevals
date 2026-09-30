"""The single file policy for eval hashing and execution."""
import base64
import hashlib
from pathlib import Path

JUNK_NAMES = {".DS_Store", "__pycache__", ".pytest_cache"}
RESERVED_NAMES = {"out", "cache", "lib"}


def eval_files(folder: Path):
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"{path}: symlinks are not allowed in an eval folder")
        if path.is_file() and path.stat().st_nlink > 1:
            raise ValueError(f"{path}: hard links are not allowed in an eval folder")
        parts = path.relative_to(folder).parts
        if parts[0] == "scorer" and path.name in RESERVED_NAMES:
            raise ValueError(f"{path}: reserved names are not allowed under scorer/")
        reserved = parts[0] in RESERVED_NAMES or (len(parts) > 1 and parts[0] == "workspace" and parts[1] in RESERVED_NAMES)
        if path.is_file() and not reserved and not JUNK_NAMES.intersection(parts):
            yield path


def manifest(folder: Path) -> dict[str, bytes]:
    # Complete validation precedes every read, including configuration reads.
    paths = list(eval_files(folder))
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in paths}


def content_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        name = name.encode()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def inline_file(data: bytes) -> str:
    return "data:application/octet-stream;base64," + base64.b64encode(data).decode()
