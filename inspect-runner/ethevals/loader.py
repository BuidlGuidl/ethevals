import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from inspect_ai.dataset import Sample
from pydantic import Field

from .config import Config, Declaration, Mode, parse_file, read_yaml
from .scorers import SCORERS, TargetScorer

PILLARS = {"concepts", "transactions", "building", "security"}


class EvalDeclaration(Declaration):
    prompt: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    type: Literal["quiz", "scenario", "build", "act"]
    modes: list[Mode] = Field(min_length=1)
    choices: list[str] | None = Field(default=None, min_length=2, max_length=26)


# These local artifacts never form part of an eval, including before git add.
IGNORED_NAMES = {".DS_Store", "out", "cache", "lib", "__pycache__", ".pytest_cache"}


def eval_files(folder: Path):
    for path in sorted(folder.iterdir()):
        if path.name in IGNORED_NAMES:
            continue
        if path.is_symlink():
            raise ValueError(f"{path}: symlinks are not allowed in an eval folder")
        if path.is_dir():
            yield from eval_files(path)
        elif path.is_file():
            yield path


def eval_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in eval_files(folder):
        if path.is_file():
            name = path.relative_to(folder).as_posix().encode()
            data = path.read_bytes()
            digest.update(len(name).to_bytes(8, "big") + name)
            digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


@dataclass(frozen=True)
class Eval:
    folder: Path
    id: str
    hash: str
    pillar: str
    declaration: EvalDeclaration
    scorer: Declaration

    def sample(self) -> Sample:
        # Only workspace files are eligible for copying into a future sandbox.
        files = {
            f"/workspace/{path.relative_to(self.folder / 'workspace').as_posix()}": str(path)
            for path in eval_files(self.folder / "workspace")
        }
        return Sample(
            id=self.id, input=self.declaration.prompt,
            target=getattr(self.scorer, "target", ""), choices=self.declaration.choices,
            files=files, metadata={"eval_id": self.id, "eval_hash": self.hash,
                                   "pillar": self.pillar, "type": self.declaration.type},
        )


def load_eval(folder: Path, config: Config) -> Eval:
    folder = folder.resolve()
    declaration = parse_file(EvalDeclaration, folder / "eval.yaml")
    if folder.parent.name not in PILLARS:
        raise ValueError(f"{folder / 'eval.yaml'}: pillar must be one of {sorted(PILLARS)}")
    for name in ("workspace", "scorer"):
        if not (folder / name).is_dir():
            raise ValueError(f"{folder / name}: {name}: required directory is missing")
    path = folder / "scorer" / "scorer.yaml"
    kind = read_yaml(path).get("kind")
    if not isinstance(kind, str) or kind not in SCORERS:
        raise ValueError(f"{path}: kind: unknown scorer kind {kind!r}")
    scorer_config = parse_file(SCORERS[kind].schema, path)
    if isinstance(scorer_config, TargetScorer):
        if declaration.type != "quiz":
            raise ValueError(f"{folder / 'eval.yaml'}: type: target scoring requires quiz")
        if bool(declaration.choices) != (scorer_config.method == "choice"):
            raise ValueError(f"{path}: method: choices require choice scoring and vice versa")
        if declaration.choices:
            targets = [scorer_config.target] if isinstance(scorer_config.target, str) else scorer_config.target
            valid = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:len(declaration.choices)])
            if any(target not in valid for target in targets):
                raise ValueError(f"{path}: target: must name an available choice letter")
    return Eval(folder, f"{folder.parent.name}/{folder.name}", eval_hash(folder),
                folder.parent.name, declaration, scorer_config)
