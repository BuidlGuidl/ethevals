from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from inspect_ai.dataset import Sample
from inspect_ai.tool import Skill
from pydantic import Field

from .config import Config, Declaration, Mode, parse_file
from .scorers import TargetScorer, rubric_questions
from .check_script import script_path, validate_script
from .sandboxes import IMAGES, SOLC_VERSIONS, validate_compose
from .files import manifest, content_hash, inline_file
from .skills import pack_skills

PILLARS = {"concepts", "transactions", "building", "security"}


class EvalDeclaration(Declaration):
    prompt: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    type: Literal["quiz", "scenario", "build", "act"]
    modes: list[Mode] = Field(min_length=1)
    choices: list[str] | None = Field(default=None, min_length=2, max_length=26)


@dataclass(frozen=True)
class Eval:
    folder: Path
    id: str
    hash: str
    pillar: str
    declaration: EvalDeclaration
    scorer_kinds: list[str]
    target: TargetScorer | None
    files: dict[str, bytes]
    skills: list[Skill]

    def sample(self) -> Sample:
        # Only workspace files are eligible for copying into a future sandbox.
        files = {
            f"/workspace/{name.removeprefix('workspace/')}": inline_file(data)
            for name, data in self.files.items() if name.startswith("workspace/")
        }
        notes = []
        if "tests" in self.scorer_kinds:
            files["/workspace/foundry.toml"] = inline_file((IMAGES / "foundry.toml").read_bytes())
            notes.append(
                f"Available solc versions: {', '.join(SOLC_VERSIONS)}. "
                "Use the supplied foundry.toml without changing compiler settings or remappings. "
                "OpenZeppelin and forge-std come from the image. Other Solidity dependencies must use relative imports under src/ or lib/."
            )
        return Sample(
            id=self.id, input="\n".join([self.declaration.prompt, *notes]),
            target=self.target.target if self.target else "", choices=self.declaration.choices,
            files=files, metadata={"eval_id": self.id, "eval_hash": self.hash,
                                   "pillar": self.pillar, "type": self.declaration.type},
        )


def load_eval(folder: Path, config: Config) -> Eval:
    if folder.is_symlink():
        raise ValueError(f"{folder}: symlinks are not allowed in an eval folder")
    folder = folder.resolve()
    files = manifest(folder)
    if "eval.yaml" not in files:
        raise ValueError(f"{folder / 'eval.yaml'}: required regular file is missing")
    declaration = parse_file(EvalDeclaration, folder / "eval.yaml", files["eval.yaml"])
    skills = []
    if "skills" in declaration.modes:
        pack, skills = pack_skills()
        files.update(pack)
    if declaration.type == "scenario":
        raise ValueError(f"{folder / 'eval.yaml'}: type: scenario is not supported yet")
    if any(not choice.strip() for choice in declaration.choices or []):
        raise ValueError(f"{folder / 'eval.yaml'}: choices must not contain blank entries")
    if folder.parent.name not in PILLARS:
        raise ValueError(f"{folder / 'eval.yaml'}: pillar must be one of {sorted(PILLARS)}")
    for name in ("workspace", "scorer"):
        if not (folder / name).is_dir():
            raise ValueError(f"{folder / name}: {name}: required directory is missing")
    kinds = [kind for kind, present in (
        ("target", "scorer/target.yaml" in files),
        ("tests", (folder / "scorer/tests").is_dir()),
        ("check_script", script_path(files, "check") is not None),
        ("rubric", "scorer/rubric.md" in files),
    ) if present]
    primary = {"quiz": "target", "build": "tests", "act": "check_script"}.get(declaration.type)
    if primary not in kinds or set(kinds) - {primary, "rubric"}:
        raise ValueError(f"{folder / 'scorer'}: scorer files do not match type {declaration.type}")
    target = None
    if "target" in kinds:
        path = folder / "scorer/target.yaml"
        target = parse_file(TargetScorer, path, files["scorer/target.yaml"])
        if declaration.choices:
            targets = [target.target] if isinstance(target.target, str) else target.target
            valid = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:len(declaration.choices)])
            if any(value not in valid for value in targets):
                raise ValueError(f"{path}: target must name an available choice letter")
        validate_hf_export(declaration, target, str(path))
    if "tests" in kinds:
        if "workspace/foundry.toml" in files:
            raise ValueError(f"{folder}: workspace/foundry.toml is runner-owned; remove the author's file")
        if not any(name.startswith("scorer/tests/") and name.endswith(".t.sol") for name in files):
            raise ValueError(f"{folder}: scorer/tests must contain a .t.sol file")
    if "rubric" in kinds:
        rubric_questions(files)
    if "check_script" in kinds:
        validate_script(declaration, files)
    if declaration.type in {"build", "act"} and not (folder / "scorer/solution").is_dir():
        raise ValueError(f"{folder}: scorer/solution is required for build and act evals")
    if (folder / "compose.yaml").is_dir():
        raise ValueError(f"{folder / 'compose.yaml'}: must be a regular file")
    if "compose.yaml" in files:
        validate_compose(folder / "compose.yaml", data=files["compose.yaml"])
    return Eval(folder, f"{folder.parent.name}/{folder.name}", content_hash(files),
                folder.parent.name, declaration, kinds, target, files, skills)


def validate_hf_export(declaration: EvalDeclaration, target: TargetScorer, source: str) -> None:
    if declaration.type != "quiz" or "vanilla" not in declaration.modes:
        return
    if isinstance(target.target, list) and len(target.target) != 1:
        raise ValueError(f"{source}: Inspect's HF loader cannot preserve alternative targets")
