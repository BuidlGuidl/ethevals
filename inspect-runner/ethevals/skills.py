"""Read installed skills from the same captured bytes as the eval hash."""
from pathlib import Path
from tempfile import TemporaryDirectory

from inspect_ai.tool import Skill, read_skills

from .files import manifest

PACK = Path(__file__).resolve().parents[2] / "skills"
PREFIX = "/skills/"


def pack_skills() -> tuple[dict[str, bytes], list[Skill]]:
    files = {name: data for name, data in manifest(PACK).items() if "/" in name}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        try:
            skills = read_skills(sorted(path for path in root.iterdir() if path.is_dir()))
        except Exception as error:
            raise ValueError(f"{PACK}: {str(error).replace(str(root), str(PACK))}") from error
        if not skills:
            raise ValueError(f"{PACK}: the skills pack must contain at least one skill")
        for skill in skills:
            for kind in (skill.scripts, skill.references, skill.assets):
                for name, path in kind.items():
                    kind[name] = path.read_bytes()
        return {PREFIX + name: data for name, data in files.items()}, skills


def skill_index(skills: list[Skill]) -> str:
    return "# Ethereum skills\n\nRead the installed skills that apply to the task.\n\n" + "\n".join(
        f"- {skill.name}: {skill.description}" for skill in skills
    ) + "\n"
