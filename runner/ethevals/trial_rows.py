"""Build board rows from Harbor's saved trials."""
import json
import logging
from pathlib import Path
import re

from harbor.models.trial.result import TrialResult
from harbor.models.job.lock import TaskLock

from .checks import JudgeError, read_details, read_reward

SCHEMA_VERSION = 8


def trial_identity(row: dict) -> tuple:
    return tuple(row.get(key) for key in (
        "task_id", "task_hash", "skills_hash", "agent", "model", "effort", "mode", "trial"))


def results_row(folder: Path, metadata: dict, *, trajectory_url: str | None = None) -> dict:
    lock = TaskLock.model_validate(json.loads((folder / "lock.json").read_text())["task"])
    if lock.digest != metadata["task_hash"]:
        raise ValueError(f"{folder / 'lock.json'}: task digest differs from the plan")
    result = TrialResult.model_validate_json((folder / "result.json").read_text())
    error = result.exception_info
    timed_out = error is not None and error.exception_type == "AgentTimeoutError"
    timeout = re.fullmatch(r"(?:Agent|Verifier) execution timed out after ([0-9.eE+-]+) seconds", error.exception_message) if (
        error and error.exception_type in {"AgentTimeoutError", "VerifierTimeoutError"}) else None
    reason = error.exception_message if error and not timed_out else None
    kind = error.exception_type if reason else None
    rewards, checks = {}, {}
    judge = metadata.get("judge")
    judge_cost, judge_paid_by = (None if judge else 0.0), metadata.get("judge_paid_by")
    try:
        details = read_details(folder / "verifier")
        judges = [detail for detail in details if detail.get("kind") in {"llm", "agent", "jev"}]
        if judge:
            costs = [detail.get("usage", {}).get("cost_usd") for detail in judges]
            judge_cost = (0.0 if judge_paid_by == "free" else
                          sum(costs) if costs and all(type(cost) in (int, float) for cost in costs) else None)
        rewards, checks = read_reward(folder / "verifier", details=details)
        if judge:
            if not judges:
                raise JudgeError("The verifier did not record the planned judge.", rewards, checks)
            for detail in judges:
                settings = detail["judge"]
                if settings["model"] != judge["model"] or settings.get("reasoning_effort") != judge["effort"]:
                    raise JudgeError("The verifier judge differs from the planned judge.", rewards, checks)
    except JudgeError as exc:
        rewards, checks = exc.rewards, exc.checks
        if not reason:
            kind, reason = "judge", str(exc)
    except ValueError as exc:
        if not reason:
            kind, reason = error.exception_type if error else "verification", str(exc)
    if result.finished_at is None:
        kind, reason = "execution", "The trial did not finish."
    if result.agent_info.version != metadata["agent_version"]:
        kind, reason = "agent_version", f"Expected agent version {metadata['agent_version']}; got {result.agent_info.version}."
    if not reason:
        saved = result.verifier_result.rewards if result.verifier_result else None
        if saved != rewards:
            kind, reason = error.exception_type if error else "verification", "Harbor's saved rewards differ from reward.json."
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
            "task_id", "task_hash", "skills_hash", "agent", "model", "effort", "mode", "trial", "retry",
            "paid_by", "agent_version", "harbor_version")},
        "completed_at": result.finished_at.isoformat() if result.finished_at else None,
        "status": "error" if reason else "passed" if rewards.get("reward") == 1 else "failed",
        "rewards": rewards,
        "checks": checks, "error_kind": kind, "error_reason": " ".join(reason.split()) if reason else None,
        "limit": {"type": "time", "limit": float(timeout[1]), "reason": error.exception_message} if timeout else None,
        "total_tokens": (n_input or 0) + (n_output or 0),
        "model_cost_usd": cost, "judge_cost_usd": judge_cost, "judge": judge, "judge_paid_by": judge_paid_by,
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
            url, old_url = row.get("trajectory_url") or "", (old or {}).get("trajectory_url") or ""
            if old is None or (row["retry"], row.get("completed_at") or "", url.startswith("https://"), url.startswith("https://hub.harborframework.com/jobs/")) > (
                old["retry"], old.get("completed_at") or "", old_url.startswith("https://"), old_url.startswith("https://hub.harborframework.com/jobs/")):
                latest[identity] = row
    return sorted(latest.values(), key=lambda row: tuple(str(value or "") for value in trial_identity(row)[:-1]) + (row["trial"],))


def recover_rows(output: Path) -> list[dict]:
    rows = []
    from .hub import trial_url
    from .secret_check import RECEIPT
    for receipt in sorted((output / "jobs").glob(f"*/{RECEIPT}")):
        withheld = json.loads(receipt.read_text()).get("withheld")
        if withheld:
            rows.append(withheld)
    for board_path in sorted((output / "jobs").glob("*/board.json")):
        receipt = board_path.parent / RECEIPT
        if receipt.is_file() and json.loads(receipt.read_text()).get("withheld"):
            continue
        metadata = json.loads(board_path.read_text())
        for result in sorted(board_path.parent.glob("*/result.json")):
            try:
                row = results_row(result.parent, metadata, trajectory_url=trial_url(result.parent))
            except (ValueError, OSError, KeyError) as error:
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
