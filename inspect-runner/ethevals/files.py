"""The single file policy for eval hashing and execution."""
import base64
import hashlib
from pathlib import Path

IGNORED_NAMES = {".DS_Store", "out", "cache", "lib", "__pycache__", ".pytest_cache"}


def eval_files(folder: Path, *, scorer=False, ignored=False):
    for path in sorted(folder.iterdir()):
        if path.is_symlink():
            raise ValueError(f"{path}: symlinks are not allowed in an eval folder")
        private = scorer or path.name == "scorer"
        reserved = path.name in IGNORED_NAMES
        if private and reserved:
            raise ValueError(f"{path}: reserved names are not allowed under scorer/")
        skip = ignored or reserved
        if path.is_dir():
            yield from eval_files(path, scorer=private, ignored=skip)
        elif path.is_file() and not skip:
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
