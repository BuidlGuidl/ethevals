import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from inspect_ai.dataset import Sample
from pydantic import Field
from pydantic import ValidationError

from .config import Config, Declaration, Mode, parse_file, read_yaml
from .scorers import SCORERS
from .sandboxes import validate_compose

PILLARS = {"concepts", "transactions", "building", "security"}


class EvalDeclaration(Declaration):
    prompt: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    type: Literal["quiz", "scenario", "build", "act"]
    modes: list[Mode] = Field(min_length=1)
    choices: list[str] | None = Field(default=None, min_length=2, max_length=26)
    time_limit: int | None = Field(default=None, gt=0)


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
    scorers: list[Declaration]

    def sample(self) -> Sample:
        # Only workspace files are eligible for copying into a future sandbox.
        files = {
            f"/workspace/{path.relative_to(self.folder / 'workspace').as_posix()}": str(path)
            for path in eval_files(self.folder / "workspace")
        }
        fields = {}
        for item in self.scorers:
            fields.update(SCORERS[item.kind].sample_fields(item))
        return Sample(
            id=self.id, input=self.declaration.prompt,
            **fields, choices=self.declaration.choices,
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
    raw = read_yaml(path)
    # Preserve the original single-kind form for existing target evals.
    if "scorers" in raw:
        if set(raw) != {"scorers"}:
            raise ValueError(f"{path}: only scorers is allowed beside a scorer list")
        items = raw["scorers"]
    else:
        items = [raw]
    if not isinstance(items, list) or not items:
        raise ValueError(f"{path}: scorers must be a nonempty list")
    scorers, kinds = [], set()
    for item in items:
        kind = item.get("kind") if isinstance(item, dict) else None
        if not isinstance(kind, str) or kind not in SCORERS or kind in kinds:
            raise ValueError(f"{path}: kind: unknown or repeated scorer kind {kind!r}")
        entry = SCORERS[kind]
        try:
            scorer_config = entry.schema.model_validate(item)
            entry.validate(scorer_config, declaration, folder)
        except ValidationError as error:
            details = "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors(include_input=False))
            raise ValueError(f"{path}: {details}") from error
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error
        scorers.append(scorer_config)
        kinds.add(kind)
    if declaration.type in {"build", "act"} and not (folder / "scorer/solution").is_dir():
        raise ValueError(f"{folder}: scorer/solution is required for build and act evals")
    if (folder / "compose.yaml").exists():
        validate_compose(folder / "compose.yaml")
    return Eval(folder, f"{folder.parent.name}/{folder.name}", eval_hash(folder),
                folder.parent.name, declaration, scorers)
