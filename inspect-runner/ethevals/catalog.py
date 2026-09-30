import json
from pathlib import Path

from .loader import Eval


def write_catalog(evals: list[Eval], output: Path) -> Path:
    """Export public declarations with the identities supplied by the loader."""
    entries = [dict(evaluation.declaration.model_dump(), id=evaluation.id,
                    hash=evaluation.hash, pillar=evaluation.pillar)
               for evaluation in evals]
    output.mkdir(parents=True, exist_ok=True)
    path = output / "catalog.json"
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n")
    return path
