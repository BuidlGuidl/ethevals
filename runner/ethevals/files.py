"""Capture skills files, hash paths with their bytes, and write small files whole."""
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


def write_whole(path: Path, text: str, scratch: Path) -> None:
    """Replace a file in one step, so a run killed mid-write never leaves it half written.

    The temporary file goes in scratch, outside any job folder the publication check fingerprints.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    temporary = scratch / f".{path.parent.name}.{path.name}.tmp"
    temporary.write_text(text)
    temporary.replace(path)


def content_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        name = name.encode()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()
