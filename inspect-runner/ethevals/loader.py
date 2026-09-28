from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from inspect_ai.dataset import Sample
from pydantic import Field
from pydantic import ValidationError

from .config import Config, Declaration, Mode, parse_file, read_yaml
from .scorers import SCORERS
from .sandboxes import validate_compose
from .files import manifest, content_hash, inline_file

PILLARS = {"concepts", "transactions", "building", "security"}


class EvalDeclaration(Declaration):
    prompt: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    type: Literal["quiz", "scenario", "build", "act"]
    modes: list[Mode] = Field(min_length=1)
    choices: list[str] | None = Field(default=None, min_length=2, max_length=26)
    time_limit: int | None = Field(default=None, gt=0)


def eval_hash(folder: Path) -> str:
    return content_hash(manifest(folder))


@dataclass(frozen=True)
class Eval:
    folder: Path
    id: str
    hash: str
    pillar: str
    declaration: EvalDeclaration
    scorers: list[Declaration]
    files: dict[str, bytes]
    test_checks: tuple[str, ...] = ()

    def sample(self) -> Sample:
        # Only workspace files are eligible for copying into a future sandbox.
        files = {
            f"/workspace/{name.removeprefix('workspace/')}": inline_file(data)
            for name, data in self.files.items() if name.startswith("workspace/")
        }
        fields, notes = {}, []
        for item in self.scorers:
            fields.update(SCORERS[item.kind].sample_fields(item))
            supplied, note = SCORERS[item.kind].workspace(item)
            files.update({f"/workspace/{name}": inline_file(data) for name, data in supplied.items()})
            if note:
                notes.append(note)
        return Sample(
            id=self.id, input="\n".join([self.declaration.prompt, *notes]),
            **fields, choices=self.declaration.choices,
            files=files, metadata={"eval_id": self.id, "eval_hash": self.hash,
                                   "pillar": self.pillar, "type": self.declaration.type},
        )


def load_eval(folder: Path, config: Config) -> Eval:
    if folder.is_symlink():
        raise ValueError(f"{folder}: symlinks are not allowed in an eval folder")
    folder = folder.resolve()
    files = manifest(folder)
    for name in ("eval.yaml", "scorer/scorer.yaml"):
        if name not in files:
            raise ValueError(f"{folder / name}: required regular file is missing")
    declaration = parse_file(EvalDeclaration, folder / "eval.yaml", files["eval.yaml"])
    if folder.parent.name not in PILLARS:
        raise ValueError(f"{folder / 'eval.yaml'}: pillar must be one of {sorted(PILLARS)}")
    for name in ("workspace", "scorer"):
        if not (folder / name).is_dir():
            raise ValueError(f"{folder / name}: {name}: required directory is missing")
    path = folder / "scorer" / "scorer.yaml"
    raw = read_yaml(path, files["scorer/scorer.yaml"])
    if set(raw) != {"scorers"}:
        raise ValueError(f"{path}: expected only scorers; unexpected keys {sorted(set(raw) - {'scorers'})}")
    items = raw["scorers"]
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
            entry.validate(scorer_config, declaration, files)
        except ValidationError as error:
            details = "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors(include_input=False))
            raise ValueError(f"{path}: {details}") from error
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error
        scorers.append(scorer_config)
        kinds.add(kind)
    if "rubric" in kinds and ("tests" not in kinds or [item.kind for item in scorers].index("rubric") < [item.kind for item in scorers].index("tests")):
        raise ValueError(f"{path}: rubric requires tests before it to supply compiled evidence")
    if declaration.type in {"build", "act"} and not (folder / "scorer/solution").is_dir():
        raise ValueError(f"{folder}: scorer/solution is required for build and act evals")
    if (folder / "compose.yaml").is_dir():
        raise ValueError(f"{folder / 'compose.yaml'}: must be a regular file")
    if "compose.yaml" in files:
        validate_compose(folder / "compose.yaml", data=files["compose.yaml"])
    return Eval(folder, f"{folder.parent.name}/{folder.name}", content_hash(files),
                folder.parent.name, declaration, scorers, files)
