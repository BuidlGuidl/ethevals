import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from inspect_ai.log import EvalLog, EvalSample, read_eval_log


def results_rows(log: EvalLog) -> list[dict]:
    metadata = log.eval.metadata or {}
    location = unquote(urlparse(log.location).path) if log.location.startswith("file://") else log.location
    samples = list(log.samples or [])
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
            for name, check in (score.metadata or {}).get("checks", {}).items():
                if name in checks:
                    raise ValueError(f"{log.location}: duplicate check {name}")
                checks[name] = check
        error = sample.error.message if sample.error else None
        error_kind = "execution" if error else None
        if sample.limit:
            error_kind = f"{sample.limit.type}_limit"
            error = sample.limit.reason or f"Epoch reached {sample.limit.type} limit {sample.limit.limit}."
        if not checks and not error:
            error_kind, error = "scoring", "The epoch produced no named checks."
        usage = list(sample.model_usage.values())
        total_tokens = sum(item.total_tokens for item in usage)
        grader = sample.role_usage.get("grader")
        grader_tokens = grader.total_tokens if grader else 0
        cost = sum(item.total_cost for item in usage) if all(item.total_cost is not None for item in usage) else None
        if metadata.get("answer_kind"):
            cost, cost_source = 0.0, "mock"
        else:
            cost_source = metadata["cost_source"] if cost is not None else "unavailable"
        passed = None if error else all(check["passed"] for check in checks.values())
        rows.append({
            "schema_version": 1,
            **{key: metadata.get(key) for key in (
                "eval_id", "eval_hash", "pillar", "type", "mode", "harness", "model", "effort", "answer_kind",
                "grader_model", "grader_effort",
            )},
            "epoch": sample.epoch,
            "status": "error" if error else "passed" if passed else "failed",
            "passed": passed,
            "checks_json": json.dumps(checks, sort_keys=True),
            "error_kind": error_kind,
            "error_reason": " ".join(error.split()) if error else None,
            "model_tokens": total_tokens - grader_tokens,
            "grader_tokens": grader_tokens,
            "total_tokens": total_tokens,
            "token_source": "mock" if metadata.get("answer_kind") else "provider",
            "cost_usd": cost,
            "cost_source": cost_source,
            "prices_json": json.dumps(metadata.get("prices", {}), sort_keys=True),
            "grader_prices_json": json.dumps(metadata.get("grader_prices", {}), sort_keys=True),
            "working_seconds": sample.working_time,
            "total_seconds": sample.total_time,
            "log_file": location,
            "log_sample_id": sample.id,
            "log_epoch": sample.epoch,
            "sample_uuid": sample.uuid,
        })
    return rows


def export_rows(logs: list[EvalLog], destination: Path) -> list[dict]:
    rows = [row for log in logs for row in results_rows(read_eval_log(log.location))]
    rows.sort(key=lambda row: (row["eval_id"], row["model"], row["mode"], row["epoch"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    temporary.replace(destination)
    return rows
