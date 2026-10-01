"""Read installed skills and hash their captured bytes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

from inspect_ai.tool import Skill, read_skills
from inspect_ai.tool._tools._skill.read import SkillParsingError

from .files import content_hash, manifest

PACK = Path(__file__).resolve().parents[2] / "skills"
PREFIX = "/skills/"


class SkillsPack(NamedTuple):
    files: dict[str, bytes]
    skills: list[Skill]
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
            skills = read_skills(sorted(path for path in root.iterdir() if path.is_dir()))
        except (OSError, ValueError, SkillParsingError) as error:
            raise ValueError(f"{PACK}: {str(error).replace(str(root), str(PACK))}") from error
        if not skills:
            raise ValueError(f"{PACK}: the skills pack must contain at least one skill")
        for skill in skills:
            for kind in (skill.scripts, skill.references, skill.assets):
                for name, path in kind.items():
                    kind[name] = path.read_bytes()
        captured = {PREFIX + name: data for name, data in files.items()}
        return SkillsPack(captured, skills, content_hash(captured))


def skill_index(skills: list[Skill]) -> str:
    return "# Ethereum skills\n\nRead the installed skills that apply to the task.\n\n" + "\n".join(
        f"- {skill.name}: {skill.description}" for skill in skills
    ) + "\n"
