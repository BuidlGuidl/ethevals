"""Check trial files while credentials exist, then admit only those bytes to publication."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

from harbor.models.task.task import Task
from harbor.utils.env import get_required_host_vars, is_sensitive_env_key

from .job_config import JobSettings

RECEIPT = "publication-check.json"
MIN_SECRET_BYTES = 8


def task_host_variables(path: Path) -> list[str]:
    """Return a task's declared host-variable names."""
    return Task(path).config.metadata.get("required_env", [])


def secret_values(config: JobSettings, paths: list[Path]) -> dict[str, set[bytes]]:
    values = {}

    def add(name, value):
        if isinstance(value, str) and len(value.encode()) >= MIN_SECRET_BYTES:
            values.setdefault(name, set()).add(value.encode())

    def auth_tokens(value, name="CODEX_AUTH_JSON"):
        if isinstance(value, dict):
            for key, child in value.items():
                label = f"{name}.{key}"
                if isinstance(child, (dict, list)):
                    auth_tokens(child, label)
                elif is_sensitive_env_key(key):
                    add(label, child)
        elif isinstance(value, list):
            for child in value:
                auth_tokens(child, name)

    names = ({config.judge.key_env} | {name for agent in config.agents.values() for name in agent.required_env}
             | {name for path in paths for name in task_host_variables(path)})
    for name in names:
        add(name, os.environ.get(name))
    for agent in config.agents.values():
        environment = dict(os.environ)
        for name, value in agent.env.items():
            hosts = get_required_host_vars({name: value})
            if hosts:
                host, default = hosts[0]
                value = os.environ.get(host, default)
                add(host, value)
                add(name, value)
            elif is_sensitive_env_key(name):
                # A literal setting such as a base URL or model name isn't a secret.
                add(name, value)
            environment[name] = value
        for credential in agent.required_files:
            hosts = get_required_host_vars({"path": credential.path})
            filename = (environment.get(hosts[0][0]) or hosts[0][1]) if hosts else credential.path
            if filename:
                path = Path.home() / filename[2:] if filename.startswith("~/") else Path(filename)
                if path.is_file():
                    try:
                        auth_tokens(json.loads(path.read_text()))
                    except (OSError, ValueError):
                        raise ValueError("Cannot read credential tokens for the publication check") from None
    if os.environ.get("CODEX_AUTH_JSON"):
        try:
            auth_tokens(json.loads(os.environ["CODEX_AUTH_JSON"]))
        except ValueError:
            raise ValueError("Cannot read CODEX_AUTH_JSON for the publication check") from None
    return values


def check_folder(folder: Path, secrets: dict[str, set[bytes]]) -> tuple[list[str], str]:
    """Check every filename and byte, including binary files, and return names and a digest."""
    found, digest = set(), hashlib.sha256()
    overlap = max((len(value) for values in secrets.values() for value in values), default=1) - 1

    def matches(data):
        found.update(name for name, values in secrets.items() if any(value in data for value in values))

    try:
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Publication requires a regular folder")
        for path in sorted(folder.rglob("*")):
            mode = path.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError("Publication forbids symlinks and special files")
            name = path.relative_to(folder).as_posix().encode()
            matches(name)
            if path.name == RECEIPT and path.parent == folder:
                matches(path.read_bytes())
                continue
            digest.update(len(name).to_bytes(8) + name)
            if stat.S_ISDIR(mode):
                digest.update(b"directory")
                continue
            digest.update(path.stat().st_size.to_bytes(8))
            tail = b""
            with path.open("rb") as file:
                while chunk := file.read(1024 * 1024):
                    matches(tail + chunk)
                    tail = (tail + chunk)[-overlap:] if overlap else b""
                    digest.update(chunk)
    except OSError:
        raise ValueError("Cannot read trial files for the publication check") from None
    return sorted(found), digest.hexdigest()


def remember_secrets(folder: Path, secrets: dict[str, set[bytes]]) -> None:
    """Keep secret fingerprints outside the artifact so an interrupted job cannot lose its inventory."""
    inventory = folder.parent.parent / ".publication-secrets" / f"{folder.name}.json"
    if inventory.exists():
        return
    if (folder / "config.json").exists() or any(folder.glob("*/result.json")):
        try:
            require_checked(folder)
        except ValueError:
            return
    inventory.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text(json.dumps({name: sorted(hashlib.sha256(value).hexdigest() for value in values)
                                     for name, values in secrets.items()}) + "\n")


def check_output(output: Path, secrets: dict[str, set[bytes]], *, require_inventory: bool = False) -> None:
    """Keep raw files local; record a safe error row when a whole Harbor job is withheld."""
    from .trial_rows import SCHEMA_VERSION

    for board in sorted((output / "jobs").glob("*/board.json")):
        folder = board.parent
        receipt = folder / RECEIPT
        if receipt.is_file() and json.loads(receipt.read_text()).get("withheld"):
            continue
        metadata = json.loads(board.read_text())
        missing = []
        try:
            if require_inventory:
                if receipt.is_file():
                    try:
                        require_checked(folder)
                        continue
                    except ValueError:
                        pass
                inventory = output / ".publication-secrets" / f"{folder.name}.json"
                recorded = json.loads(inventory.read_text())
                available = {name: {hashlib.sha256(value).hexdigest() for value in values}
                             for name, values in secrets.items()}
                missing = [name for name, hashes in recorded.items() if set(hashes) - available.get(name, set())]
                if missing:
                    raise ValueError
            names, digest = check_folder(folder, secrets)
            reason = f"Trial withheld: secret found for {', '.join(names)}. Rotate the credential." if names else None
            kind = "secret"
        except (ValueError, OSError):
            names, digest = [], None
            kind, reason = "publication", "Trial withheld: its files could not pass the publication check."
            if missing:
                reason = f"Trial withheld: original credentials unavailable for {', '.join(missing)}."
        record = {"digest": digest}
        if reason:
            row = {"schema_version": SCHEMA_VERSION,
                   **{key: metadata.get(key) for key in (
                       "task_id", "task_hash", "skills_hash", "agent", "model", "effort", "mode", "trial", "retry",
                       "paid_by", "agent_version", "harbor_version")},
                   "completed_at": datetime.now(timezone.utc).isoformat(),
                   "status": "error", "error_kind": kind, "error_reason": reason,
                   "checks": {}, "rewards": {}, "limit": None, "total_tokens": 0,
                   "model_cost_usd": None, "judge_cost_usd": None, "judge": metadata.get("judge"),
                   "judge_paid_by": None, "judge_attempts": 0, "cost_source": "unavailable",
                   "total_seconds": None, "working_seconds": None,
                   "trajectory_file": None, "trajectory_url": None, "verifier_files": None}
            # Metadata can contain a leaked value too. Never carry it into the safe row.
            encoded = json.dumps(row)
            for values in secrets.values():
                for value in values:
                    encoded = encoded.replace(json.dumps(value.decode())[1:-1], "[withheld]")
            record = {"withheld": json.loads(encoded)}
            prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") == "true" else ""
            print(prefix + reason, file=sys.stderr)
        receipt.write_text(json.dumps(record, sort_keys=True) + "\n")


def require_checked(folder: Path) -> None:
    """Refuse files that lack a check or changed after it, even without credentials."""
    try:
        record = json.loads((folder / RECEIPT).read_text())
        if set(record) != {"digest"} or record["digest"] != check_folder(folder, {})[1]:
            raise ValueError
    except (OSError, ValueError):
        raise ValueError("Trial files lack a current publication check; run the check where credentials are available") from None


def stage_artifact(output: Path, destination: Path) -> None:
    """Copy checked jobs and safe error rows into the matrix artifact directory."""
    from .trial_rows import recover_rows, write_rows

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".publication-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "checked"
        staged.mkdir()
        for receipt in sorted((output / "jobs").glob(f"*/{RECEIPT}")):
            record = json.loads(receipt.read_text())
            target = staged / "jobs" / receipt.parent.name
            if record.get("withheld"):
                target.mkdir(parents=True)
                shutil.copyfile(receipt, target / RECEIPT)
            else:
                require_checked(receipt.parent)
                shutil.copytree(receipt.parent, target)
                require_checked(target)
        if destination.exists():
            shutil.rmtree(destination)
        staged.replace(destination)
    write_rows(destination / "rows.jsonl", recover_rows(destination))
