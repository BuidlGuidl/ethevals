"""Capture skills files and hash paths with their bytes."""
import hashlib
from pathlib import Path

JUNK_NAMES = {".DS_Store", "__pycache__", ".pytest_cache"}


def manifest(folder: Path) -> dict[str, bytes]:
    paths = sorted(folder.rglob("*"))
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"{path}: symlinks are forbidden in the skills pack")
        if path.is_file() and path.stat().st_nlink > 1:
            raise ValueError(f"{path}: hard links are forbidden in the skills pack")
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in paths
            if path.is_file() and not JUNK_NAMES.intersection(path.relative_to(folder).parts)}


def content_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        name = name.encode()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()
