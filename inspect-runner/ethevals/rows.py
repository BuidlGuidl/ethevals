import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from inspect_ai.log import EvalLog, EvalSample, EvalError, list_eval_logs, read_eval_log


def epoch_identity(metadata: dict, epoch: int) -> tuple:
    return tuple(metadata.get(key) for key in (
        "eval_id", "eval_hash", "harness", "model", "effort", "mode",
    )) + (epoch,)


def results_rows(log: EvalLog) -> list[dict]:
    metadata = log.eval.metadata or {}
    location = unquote(urlparse(log.location).path) if log.location.startswith("file://") else log.location
    samples = list(log.samples or [])
    if not samples and not log.error:
        samples.append(EvalSample(id=metadata["eval_id"], epoch=1, input="", target="",
                                  error=EvalError(message="Epoch stopped before it produced a result.",
                                                  traceback="", traceback_ansi="")))
    # Setup failures can end a task before Inspect records any sample.
    if log.error:
        completed = {(sample.id, sample.epoch) for sample in samples}
        for epoch in range(1, (log.eval.config.epochs or 1) + 1):
            if (metadata["eval_id"], epoch) not in completed:
                samples.append(EvalSample(id=metadata["eval_id"], epoch=epoch, input="", target="", error=log.error))
    rows = []
    for sample in samples:
        checks = {}
        for score in (sample.scores or {}).values():
            for name, value in score.value.items():
                if name in checks:
                    raise ValueError(f"{log.location}: duplicate check {name}")
                checks[name] = {"passed": value == "C", "reason": score.metadata["reasons"][name]}
        error = sample.error.message if sample.error else None
        error_kind = "execution" if error else None
        if not checks and not error:
            error_kind, error = "scoring", "The epoch produced no named checks."
        usage = list(sample.model_usage.values())
        total_tokens = sum(item.total_tokens for item in usage)
        grader = sample.role_usage.get("grader")
        total_cost = sum(item.total_cost for item in usage) if usage and all(item.total_cost is not None for item in usage) else None
        grader_cost = grader.total_cost if grader else 0.0 if usage else None
        model_cost = total_cost - grader_cost if total_cost is not None and grader_cost is not None else None
        cost_source = metadata.get("cost_source", "unavailable")
        if model_cost is None or grader_cost is None:
            cost_source = "unavailable"
        passed = None if error else all(check["passed"] for check in checks.values())
        rows.append({
            "schema_version": 4,
            **{key: metadata.get(key) for key in (
                "eval_id", "eval_hash", "type", "mode", "harness", "model", "effort",
            )},
            "epoch": metadata.get("epoch", sample.epoch),
            "attempt": metadata.get("attempt", 1),
            "completed_at": sample.completed_at or sample.started_at or metadata.get("created_at", log.eval.created),
            "status": "error" if error else "passed" if passed else "failed",
            "checks": checks,
            "error_kind": error_kind,
            "limit": sample.limit.model_dump() if sample.limit else None,
            "error_reason": " ".join(error.split()) if error else None,
            "total_tokens": total_tokens,
            "model_cost_usd": model_cost,
            "grader_cost_usd": grader_cost,
            "working_seconds": sample.working_time,
            "total_seconds": sample.total_time,
            "log_file": location,
            "log_url": None,
            "cost_source": cost_source,
        })
    return rows


def store_rows(output: Path) -> list[dict]:
    latest = {}
    attempts = {}
    logs = [read_eval_log(info.name) for info in list_eval_logs(str(output / "logs"))]
    # Inspect's log creation time has only second precision. Samples retain
    # microseconds; task metadata supplies that precision for setup failures.
    def created(log):
        return max([(log.eval.metadata or {}).get("created_at", log.eval.created)] + [
            sample.completed_at or sample.started_at or log.eval.created for sample in log.samples or []
        ])

    for log in sorted(logs, key=lambda log: (created(log), log.location)):
        for row in results_rows(log):
            row["log_file"] = Path(row["log_file"]).resolve().relative_to(output.resolve()).as_posix()
            identity = epoch_identity(row, row["epoch"])
            attempts[identity] = attempts.get(identity, 0) + 1
            row["attempt"] = max(row["attempt"], attempts[identity])
            latest[identity] = row
    return sorted(latest.values(), key=row_sort_key)


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def row_sort_key(row):
    identity = epoch_identity(row, row["epoch"])
    return tuple(value or "" for value in identity[:-1]) + (identity[-1],)


def row_version(row):
    # Release links enrich the same observation. They cannot replace a later attempt.
    return (row.get("attempt", 1), row.get("completed_at", ""),
            row.get("status") in {"passed", "failed"},
            bool(row.get("log_url")), json.dumps(row, sort_keys=True))


def fold_rows(*groups: list[dict]) -> list[dict]:
    latest = {}
    for group in groups:
        for row in group:
            identity = epoch_identity(row, row["epoch"])
            if identity not in latest or row_version(row) > row_version(latest[identity]):
                latest[identity] = row
    return sorted(latest.values(), key=row_sort_key)


def previous_rows(output: Path, rows_file: Path | None = None) -> list[dict]:
    return fold_rows(read_rows(rows_file) if rows_file else [], read_rows(output / "rows.jsonl"), store_rows(output))


def write_rows(destination: Path, rows: list[dict]) -> None:
    content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    if destination.exists() and destination.read_text() == content:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(content)
    temporary.replace(destination)


def export_rows(output: Path, previous: list[dict] | None = None) -> list[dict]:
    rows = fold_rows(read_rows(output / "rows.jsonl"), previous or [], store_rows(output))
    write_rows(output / "rows.jsonl", rows)
    return rows
