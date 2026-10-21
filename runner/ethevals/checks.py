"""Read the check records shared by verifiers, judges, and the board."""
import json
from pathlib import Path


def read_checks(path: Path, *, field: str | None = None) -> dict:
    checks = json.loads(path.read_text())
    if field is not None:
        checks = checks[field]
    if not isinstance(checks, dict) or not checks or any(
        not isinstance(name, str) or not name.strip() or not isinstance(check, dict)
        or type(check.get("passed")) is not bool or not isinstance(check.get("reason"), str)
        or not check["reason"].strip() or len(check["reason"].splitlines()) != 1
        for name, check in checks.items()
    ):
        raise ValueError("Each check needs a name, boolean passed, and one-line reason.")
    return checks
