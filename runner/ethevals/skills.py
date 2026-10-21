"""Read installed skills and hash their captured bytes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

from harbor.skills import resolve_skills

from .files import content_hash, manifest

PACK = Path(__file__).resolve().parents[2] / "skills"
PREFIX = "/skills/"


class SkillsPack(NamedTuple):
    files: dict[str, bytes]
    hash: str


def pack_skills() -> SkillsPack:
    files = {name: data for name, data in manifest(PACK).items() if "/" in name}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        try:
            resolve_skills([root])
        except (OSError, ValueError) as error:
            raise ValueError(f"{PACK}: {str(error).replace(str(root), str(PACK))}") from error
    captured = {PREFIX + name: data for name, data in files.items()}
    return SkillsPack(captured, content_hash(captured))
