from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

from inspect_ai.dataset import Sample
from inspect_ai.tool import Skill
from pydantic import Field, model_validator

from .config import Config, Declaration, Mode, parse_file
from .scorers import TargetScorer, rubric_questions
from .check_script import script_path, validate_script
from .sandboxes import validate_compose
from .files import manifest, content_hash, inline_file
from .skills import pack_skills

PILLARS = {"concepts", "transactions", "building", "security"}


class EvalDeclaration(Declaration):
    prompt: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    chain: Literal["anvil"] | None = None
    modes: list[Mode] = Field(min_length=1)
    choices: list[str] | None = Field(default=None, min_length=2, max_length=26)

    @model_validator(mode="after")
    def check_chain(self):
        if "chain" in self.model_fields_set and self.chain is None:
            raise ValueError("chain must be anvil or absent")
        return self


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
        return Sample(
            id=self.id, input=self.declaration.prompt,
            target=self.target.target if self.target else "", choices=self.declaration.choices,
            files=files, metadata={"eval_id": self.id, "eval_hash": self.hash,
                                   "pillar": self.pillar},
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
    if any(not choice.strip() for choice in declaration.choices or []):
        raise ValueError(f"{folder / 'eval.yaml'}: choices must not contain blank entries")
    if folder.parent.name not in PILLARS:
        raise ValueError(f"{folder / 'eval.yaml'}: pillar must be one of {sorted(PILLARS)}")
    if not (folder / "scorer").is_dir():
        raise ValueError(f"{folder / 'scorer'}: required directory is missing")
    kinds = [kind for kind, present in (
        ("target", "scorer/target.yaml" in files),
        ("tests", (folder / "scorer/tests").is_dir()),
        ("check_script", script_path(files, "check") is not None),
        ("rubric", "scorer/rubric.md" in files),
    ) if present]
    if not kinds:
        raise ValueError(f"{folder / 'scorer'}: at least one scorer is required")
    if "vanilla" in declaration.modes and (declaration.chain or "tests" in kinds or
            any(name.startswith("workspace/") for name in files)):
        raise ValueError(f"{folder}: vanilla requires no chain, workspace files, or tests")
    lint_agent_text(declaration.prompt, str(folder / "eval.yaml"))
    for name, data in files.items():
        if name.startswith("workspace/"):
            try:
                value = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            lint_agent_text(value, str(folder / name))
    target = None
    if "target" in kinds:
        path = folder / "scorer/target.yaml"
        target = parse_file(TargetScorer, path, files["scorer/target.yaml"])
        if declaration.choices:
            targets = [target.target] if isinstance(target.target, str) else target.target
            valid = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:len(declaration.choices)])
            if any(value not in valid for value in targets):
                raise ValueError(f"{path}: target must name an available choice letter")
        if "rubric" not in kinds:
            validate_hf_export(declaration, target, str(path))
    if "tests" in kinds:
        if not any(name.startswith("scorer/tests/") and name.endswith(".t.sol") for name in files):
            raise ValueError(f"{folder}: scorer/tests must contain a .t.sol file")
    if "rubric" in kinds:
        rubric_questions(files)
    if "check_script" in kinds:
        validate_script(declaration, files)
    validate_check_names(files, target, folder)
    if ("tests" in kinds or declaration.chain) and not (folder / "solution").is_dir():
        raise ValueError(f"{folder}: solution is required for tests or a chain")
    if (folder / "compose.yaml").is_dir():
        raise ValueError(f"{folder / 'compose.yaml'}: must be a regular file")
    if "compose.yaml" in files:
        validate_compose(folder / "compose.yaml", data=files["compose.yaml"])
    return Eval(folder, f"{folder.parent.name}/{folder.name}", content_hash(files),
                folder.parent.name, declaration, kinds, target, files, skills)


def validate_hf_export(declaration: EvalDeclaration, target: TargetScorer, source: str) -> None:
    if "vanilla" not in declaration.modes:
        return
    if isinstance(target.target, list) and len(target.target) != 1:
        raise ValueError(f"{source}: Inspect's HF loader cannot preserve alternative targets")


AGENT_WORDS = re.compile(r"\b(?:epochs?|graders?|rubrics?|scores?|benchmarks?|evals?|being tested(?:s)?)\b", re.IGNORECASE)


def lint_agent_text(value: str, source: str) -> None:
    if match := AGENT_WORDS.search(value):
        raise ValueError(f"{source}: agent-visible text contains forbidden word {match.group()!r}")


def validate_check_names(files, target, folder):
    names = [target.name] if target else []
    if "scorer/rubric.md" in files:
        names.extend(rubric_questions(files))
    for path, data in files.items():
        if path.startswith("scorer/tests/") and path.endswith(".t.sol"):
            source = data.decode("utf-8")
            source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)
            names.extend(re.findall(r"\bfunction\s+(test\w*|compile)\s*\(", source))
    seen = set()
    for name in names:
        if name == "compile":
            raise ValueError(f"{folder}: check name 'compile' is reserved")
        if name.startswith("testFail"):
            raise ValueError(f"{folder}: testFail functions are forbidden: {name}")
        if name in seen:
            raise ValueError(f"{folder}: duplicate check name {name!r}")
        seen.add(name)
