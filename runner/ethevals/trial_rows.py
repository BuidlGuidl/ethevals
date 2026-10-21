"""Build board rows from Harbor's saved trials."""
import json
import logging
from pathlib import Path

from harbor.models.trial.result import TrialResult

from .checks import read_checks

SCHEMA_VERSION = 7


def trial_identity(row: dict) -> tuple:
    return tuple(row.get(key) for key in (
        "task_id", "task_hash", "skills_hash", "agent", "model", "effort", "mode", "trial"))


def results_row(folder: Path, metadata: dict, *, trajectory_url: str | None = None) -> dict:
    result = TrialResult.model_validate_json((folder / "result.json").read_text())
    error = result.exception_info
    timed_out = error is not None and error.exception_type == "AgentTimeoutError"
    reason = error.exception_message if error and not timed_out else None
    kind = error.exception_type if reason else None
    checks = {}
    checks_path = folder / "verifier/checks.json"
    if checks_path.exists():
        try:
            checks = read_checks(checks_path)
        except (ValueError, OSError) as exc:
            kind, reason = "verification", str(exc)
    if result.finished_at is None:
        kind, reason = "execution", "The trial did not finish."
    if result.agent_info.version != metadata["agent_version"]:
        kind, reason = "agent_version", f"Expected agent version {metadata['agent_version']}; got {result.agent_info.version}."
    if not reason:
        reward = result.verifier_result.rewards if result.verifier_result else None
        if not checks or reward != {"reward": int(all(check["passed"] for check in checks.values()))}:
            kind, reason = "verification", "Missing checks or reward disagrees with checks."
    judge = metadata.get("judge")
    judge_attempts = 0
    judge_cost, judge_paid_by = (None if judge else 0.0), None
    if judge:
        try:
            judged = json.loads((folder / "verifier/judge.json").read_text())
            judge_attempts = judged.get("attempts", 1)
            judge_paid_by, judge_cost = judged["paid_by"], judged["cost_usd"]
            if judged["judge"] != judge:
                raise ValueError("The saved judge differs from the planned judge.")
            if judged["error"]:
                raise ValueError(judged["error"])
            extra = read_checks(folder / "verifier/judge.json", field="checks")
            if set(extra) != set(metadata["criteria_names"]) or set(extra) & set(checks):
                raise ValueError("The judge must return each criteria check with a boolean and a one-line reason.")
            checks.update(extra)
        except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            if not reason:
                kind, reason = "judge", f"Cannot judge criteria: {exc}"
    n_input, _, n_output, cost = result.compute_token_cost_totals()
    if metadata["paid_by"] == "free":
        cost = 0.0
    trajectory = folder / "agent/trajectory.json"
    elapsed = (result.finished_at - result.started_at).total_seconds() if result.finished_at and result.started_at else None
    execution = result.agent_execution
    working = (execution.finished_at - execution.started_at).total_seconds() if execution and execution.finished_at and execution.started_at else None
    return {
        "schema_version": SCHEMA_VERSION,
        **{key: metadata[key] for key in (
            "task_id", "task_hash", "skills_hash", "agent", "model", "effort", "mode", "trial", "attempt",
            "paid_by", "agent_version", "harbor_version", "time_limit")},
        "completed_at": result.finished_at.isoformat() if result.finished_at else None,
        "status": "error" if reason else "passed" if all(check["passed"] for check in checks.values()) else "failed",
        "checks": checks, "error_kind": kind, "error_reason": " ".join(reason.split()) if reason else None,
        "limit": {"type": "time", "limit": metadata["time_limit"], "reason": error.exception_message} if timed_out else None,
        "total_tokens": (n_input or 0) + (n_output or 0),
        "model_cost_usd": cost, "judge_cost_usd": judge_cost, "judge": judge, "judge_paid_by": judge_paid_by,
        "judge_attempts": judge_attempts,
        "cost_source": "free" if metadata["paid_by"] == "free" else "harbor" if cost is not None else "unavailable",
        "total_seconds": elapsed, "working_seconds": working,
        "trajectory_file": str(trajectory.resolve()) if trajectory.is_file() else None,
        "trajectory_url": trajectory_url or (f"/trajectories/{result.id}.json" if trajectory.is_file() else None),
        "verifier_files": str((folder / "verifier").resolve()),
    }


def read_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    return [row for row in rows if row.get("schema_version") == SCHEMA_VERSION]


def fold_rows(*groups: list[dict]) -> list[dict]:
    latest = {}
    for group in groups:
        for row in group:
            identity = trial_identity(row)
            old = latest.get(identity)
            if old is None or (row["attempt"], row.get("completed_at") or "", row.get("judge_attempts", 0), (row.get("trajectory_url") or "").startswith("https://")) > (
                old["attempt"], old.get("completed_at") or "", old.get("judge_attempts", 0), (old.get("trajectory_url") or "").startswith("https://")):
                latest[identity] = row
    return sorted(latest.values(), key=lambda row: tuple(str(value or "") for value in trial_identity(row)[:-1]) + (row["trial"],))


def recover_rows(output: Path) -> list[dict]:
    rows = []
    for board_path in sorted((output / "jobs").glob("*/board.json")):
        metadata = json.loads(board_path.read_text())
        for result in sorted(board_path.parent.glob("*/result.json")):
            try:
                row = results_row(result.parent, metadata)
            except (ValueError, OSError) as error:
                logging.getLogger(__name__).warning("Skipping unreadable trial %s: %s", result, error)
                continue
            rows.append(row)
    return fold_rows(rows)


def previous_rows(output: Path, rows_file: Path) -> list[dict]:
    return fold_rows(read_rows(rows_file), read_rows(output / "rows.jsonl"), recover_rows(output))


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    temporary.replace(path)
