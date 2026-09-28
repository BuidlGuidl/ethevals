import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from inspect_ai.log import EvalLog, EvalSample, EvalError, list_eval_logs, read_eval_log, resolve_sample_attachments
from inspect_ai.event import ToolEvent, ModelEvent
from .search import search_result_status, search_text, CAP_MESSAGE


def infrastructure_limit(kind, working_seconds, working_limit):
    return kind == "operator" or (kind == "time" and working_limit is not None
                                  and (working_seconds is None or working_seconds < working_limit))


def search_failures(sample):
    sample = resolve_sample_attachments(sample)
    calls, results = {}, {}
    messages = list(sample.messages)
    for event in sample.events:
        if isinstance(event, ModelEvent):
            messages.extend(event.input)
        elif isinstance(event, ToolEvent):
            calls[event.id] = event.function + json.dumps(event.arguments)
            results[event.id] = (event.result, bool(event.error or event.failed))
    for message in messages:
        if message.role == "assistant":
            for call in message.tool_calls or []:
                calls[call.id] = call.function + json.dumps(call.arguments)
        elif message.role == "tool":
            results[message.tool_call_id] = (message.text, bool(message.error))
            calls.setdefault(message.tool_call_id, message.function or "")
    rate_limited = failed = capped = 0
    searches = {key for key, call in calls.items()
                if any(name in call for name in ("web_search_exa", "web_fetch_exa", "web_search_advanced_exa"))}
    for key in searches & results.keys():
        result, error = results[key]
        limited, failure = search_result_status(result)
        rate_limited += limited
        capped += CAP_MESSAGE in search_text(result)[0]
        failed += bool(error or failure)
    return {"search_calls": len(searches), "search_failed": failed, "search_rate_limited": rate_limited,
            "search_capped": capped}


def epoch_identity(metadata: dict, epoch: int) -> tuple:
    return tuple(metadata.get(key) for key in (
        "eval_id", "eval_hash", "harness", "model", "effort", "mode", "answer_kind",
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
        checks = {} if sample.scores else dict((sample.metadata or {}).get("scoring_checks", {}))
        for score in (sample.scores or {}).values():
            for name, check in (score.metadata or {}).get("checks", {}).items():
                if name in checks:
                    raise ValueError(f"{log.location}: duplicate check {name}")
                checks[name] = check
        error = sample.error.message if sample.error else None
        error_kind = "execution" if error else None
        if error:
            for name in metadata.get("check_names", []):
                checks.setdefault(name, {"passed": False, "reason": " ".join(f"No verdict: {error}".split())})
        if sample.limit:
            reason = " ".join((f"Epoch reached {sample.limit.type} limit {sample.limit.limit}. "
                               + (sample.limit.reason or "")).split())
            if infrastructure_limit(sample.limit.type, sample.working_time, metadata.get("working_limit_seconds")):
                error_kind, error = "execution", reason
            else:
                error = error_kind = None
            checks = {name: {"passed": False, "reason": reason} for name in metadata.get("check_names", checks)}
        if not checks and not error:
            error_kind, error = "scoring", "The epoch produced no named checks."
        usage = list(sample.model_usage.values())
        total_tokens = sum(item.total_tokens for item in usage)
        grader = sample.role_usage.get("grader")
        grader_tokens = grader.total_tokens if grader else 0
        total_cost = sum(item.total_cost for item in usage) if usage and all(item.total_cost is not None for item in usage) else None
        grader_cost = grader.total_cost if grader else 0.0 if usage else None
        model_cost = total_cost - grader_cost if total_cost is not None and grader_cost is not None else None
        # A grader with unknown prices must not erase a separately metered model.
        if grader and grader.total_cost is None and metadata.get("grader_model") != metadata.get("model"):
            model_usage = sample.model_usage.get(metadata.get("model"))
            model_cost = model_usage.total_cost if model_usage else None
        model_metered, grader_metered = model_cost, grader_cost
        if metadata.get("answer_kind") and usage:
            model_cost, grader_cost = 0.0, 0.0
            model_source, grader_source = "mock", "mock"
        else:
            model_source = metadata.get("cost_source", "unavailable") if model_cost is not None else "unavailable"
            grader_source = metadata.get("grader_cost_source", "unavailable") if grader_cost is not None else "unavailable"
            if usage and not grader:
                grader_source = "no_usage"
        passed = None if error else all(check["passed"] for check in checks.values())
        rows.append({
            "schema_version": 3,
            **{key: metadata.get(key) for key in (
                "eval_id", "eval_hash", "pillar", "type", "mode", "harness", "model", "effort", "answer_kind",
                "grader_model", "grader_effort", "harness_version", "images", "runner_inputs", "chain_inputs",
                "cost_limit_usd", "grader_cost_limit_usd", "max_attempts",
                "working_limit_seconds", "time_limit_seconds", "scoring_limit_seconds",
                "search_limit", "search_price_usd",
            )},
            "epoch": metadata.get("epoch", sample.epoch),
            "attempt": metadata.get("attempt", 1),
            "completed_at": sample.completed_at or sample.started_at or metadata.get("created_at", log.eval.created),
            "status": "error" if error else "passed" if passed else "failed",
            "passed": passed,
            "checks": checks,
            "error_kind": error_kind,
            "limit": sample.limit.model_dump() if sample.limit else None,
            "error_reason": " ".join(error.split()) if error else None,
            "model_tokens": total_tokens - grader_tokens,
            "grader_tokens": grader_tokens,
            "total_tokens": total_tokens,
            "token_source": "mock" if metadata.get("answer_kind") else "provider",
            "model_cost_usd": model_cost,
            "model_metered_usd": model_metered,
            "grader_metered_usd": grader_metered,
            "model_cost_source": model_source,
            "grader_cost_usd": grader_cost,
            "grader_cost_source": grader_source,
            "prices": metadata.get("prices", {}),
            "grader_prices": metadata.get("grader_prices", {}),
            "working_seconds": sample.working_time,
            "total_seconds": sample.total_time,
            "log_file": location,
            "log_sample_id": sample.id,
            "log_epoch": sample.epoch,
            "sample_uuid": sample.uuid,
            **search_failures(sample),
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
            row.get("log_file", "").startswith("results-"), json.dumps(row, sort_keys=True))


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
