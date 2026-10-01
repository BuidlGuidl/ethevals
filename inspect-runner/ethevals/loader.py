from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

from inspect_ai.dataset import Sample
from inspect_ai.tool import Skill
from pydantic import Field

from .config import Config, Declaration, Mode, parse_file
from .scorers import RUNNERS, TargetScorer, rubric_questions, runner_files, runners_for
from .sandboxes import validate_compose
from .files import manifest, content_hash, inline_file, has_solution
from .skills import SkillsPack, pack_skills

PILLARS = {"concepts", "transactions", "building", "security"}


class ForkChain(Declaration):
    fork: Literal["mainnet", "base"]
    block: int = Field(gt=0)

    @property
    def rpc_variable(self):
        return f"{self.fork.upper()}_RPC_URL"


class EvalDeclaration(Declaration):
    prompt: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    chain: Literal["anvil"] | ForkChain | None = None
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
    skills_hash: str | None

    @property
    def fork(self):
        return self.declaration.chain if isinstance(self.declaration.chain, ForkChain) else None

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


def load_eval(folder: Path, config: Config, skills_pack: SkillsPack | None = None) -> Eval:
    if folder.is_symlink():
        raise ValueError(f"{folder}: symlinks are not allowed in an eval folder")
    folder = folder.resolve()
    files = manifest(folder)
    if "eval.yaml" not in files:
        raise ValueError(f"{folder / 'eval.yaml'}: required regular file is missing")
    declaration = parse_file(EvalDeclaration, folder / "eval.yaml", files["eval.yaml"])
    eval_hash = content_hash(files)
    skills = []
    skills_hash = None
    if "skills" in declaration.modes:
        pack = skills_pack if skills_pack is not None else pack_skills()
        skills, skills_hash = pack.skills, pack.hash
        files.update(pack.files)
    if any(not choice.strip() for choice in declaration.choices or []):
        raise ValueError(f"{folder / 'eval.yaml'}: choices must not contain blank entries")
    if folder.parent.name not in PILLARS:
        raise ValueError(f"{folder / 'eval.yaml'}: pillar must be one of {sorted(PILLARS)}")
    if not (folder / "scorer").is_dir():
        raise ValueError(f"{folder / 'scorer'}: required directory is missing")
    if (folder / "scorer/tests").is_dir() and not runners_for(files):
        raise ValueError(f"{folder}: no runner claims a file in scorer/tests/")
    kinds = [kind for kind, present in (
        ("target", "scorer/target.yaml" in files),
        ("tests", bool(runners_for(files))),
        ("rubric", "scorer/rubric.md" in files),
    ) if present]
    if not kinds:
        raise ValueError(f"{folder / 'scorer'}: at least one scorer is required")
    if any(name in files for name in ("workspace/chain.json", "workspace/private.json")):
        raise ValueError(f"{folder}: chain.json and private.json belong to setup, not workspace/")
    if "vanilla" in declaration.modes and (declaration.chain or "tests" in kinds or
            any(name.startswith("workspace/") for name in files)):
        raise ValueError(f"{folder}: vanilla requires no chain, workspace files, or tests")
    if declaration.chain and "setup/setup.s.sol" not in files:
        raise ValueError(f"{folder}: chain requires setup/setup.s.sol")
    if not declaration.chain and (folder / "setup").is_dir():
        raise ValueError(f"{folder}: setup/ requires chain")
    for text in [declaration.prompt, *(declaration.choices or [])]:
        lint_agent_text(text, str(folder / "eval.yaml"))
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
        if hf_skip_reason(declaration, files) is None:
            validate_hf_export(target, str(path))
    validate_check_names(files, target, folder)
    if ("tests" in kinds or declaration.chain) and not has_solution(files):
        raise ValueError(f"{folder}: solution is required for tests or a chain")
    if (folder / "compose.yaml").is_dir():
        raise ValueError(f"{folder / 'compose.yaml'}: must be a regular file")
    if "compose.yaml" in files:
        validate_compose(folder / "compose.yaml", data=files["compose.yaml"])
    return Eval(folder, f"{folder.parent.name}/{folder.name}", eval_hash,
                folder.parent.name, declaration, kinds, target, files, skills, skills_hash)


def validate_hf_export(target: TargetScorer, source: str) -> None:
    if isinstance(target.target, list) and len(target.target) != 1:
        raise ValueError(f"{source}: Inspect's HF loader cannot preserve alternative targets")


def hf_skip_reason(declaration, files):
    if "scorer/target.yaml" not in files:
        return "target.yaml is absent"
    if "vanilla" not in declaration.modes:
        return "vanilla mode is not declared"
    if "scorer/rubric.md" in files:
        return "rubric cannot be exported"


AGENT_WORDS = re.compile(r"\b(?:epochs?|graders?|rubrics?|scores?|benchmarks?|evals?|being\s+tested)\b", re.IGNORECASE)


def lint_agent_text(value: str, source: str) -> None:
    if match := AGENT_WORDS.search(value):
        raise ValueError(f"{source}: agent-visible text contains forbidden word {match.group()!r}")


def validate_check_names(files, target, folder):
    names = [target.name] if target else []
    if "scorer/rubric.md" in files:
        names.extend(rubric_questions(files))
    for runner in RUNNERS:
        for path, data in runner_files(runner, files).items():
            names.extend(runner.names(data.decode("utf-8")))
    seen = set()
    for name in names:
        if name == "compile":
            raise ValueError(f"{folder}: check name 'compile' is reserved")
        if name.startswith("testFail"):
            raise ValueError(f"{folder}: testFail functions are forbidden: {name}")
        if name in seen:
            raise ValueError(f"{folder}: duplicate check name {name!r}")
        seen.add(name)
