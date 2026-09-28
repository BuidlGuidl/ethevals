"""Select epochs once for both the budget plan and the runner."""
from .rows import epoch_identity
from .scorers import rubric_budget


def epoch_selection(evals, config, players, previous, epochs=None, fresh=False, retry_errors=False):
    prior = {epoch_identity(row, row["epoch"]): row for row in previous}
    selected, pending, exhausted = set(), [], []
    for evaluation in evals:
        for mode, actor in players(evaluation):
            for epoch in range(1, (epochs or config.epochs) + 1):
                identity = epoch_identity({"eval_id": evaluation.id, "eval_hash": evaluation.hash,
                                           **actor.metadata, "mode": mode}, epoch)
                selected.add(identity)
                row = prior.get(identity, {})
                attempt = row.get("attempt", 0)
                if fresh or (row.get("status") not in {"passed", "failed"}
                             and (attempt < config.max_attempts or retry_errors)):
                    pending.append((evaluation, mode, actor, epoch, attempt + 1))
                elif row.get("status") == "error":
                    exhausted.append(row)
    if not selected:
        raise ValueError("No evals declare a selected mode")
    return selected, pending, exhausted


def plan(evals, config, players, previous, *, epochs=None, retry_errors=False):
    _, pending, exhausted = epoch_selection(evals, config, players, previous, epochs, retry_errors=retry_errors)
    missing = []
    for evaluation, mode, actor, epoch, attempt in pending:
        metadata = {"eval_id": evaluation.id, "eval_hash": evaluation.hash, "type": evaluation.declaration.type,
                    **actor.metadata, "mode": mode, "epoch": epoch}
        # Reserve every remaining runner attempt. Runtime spends one per invocation.
        remaining = max(1, config.max_attempts - attempt + 1)
        per_attempt = config.cost_limit + rubric_budget(evaluation, config)
        history = [row["model_cost_usd"] + row["grader_cost_usd"] for row in previous
                   if all(row.get(key) == metadata.get(key) for key in ("type", "model", "harness", "effort", "mode", "answer_kind"))
                   and row.get("model_cost_usd") is not None and row.get("grader_cost_usd") is not None]
        missing.append({**metadata, "attempt": attempt, "remaining_attempts": remaining,
                        "per_attempt_usd": per_attempt, "worst_case_usd": per_attempt * remaining,
                        "expected_usd_estimate": sum(history) / len(history) if history else None})
    return {"missing": missing, "missing_epochs": len(missing),
            "exhausted_errors": exhausted,
            "worst_case_usd": round(sum(row["worst_case_usd"] for row in missing), 8),
            "expected_usd_estimate": round(sum(row["expected_usd_estimate"] for row in missing), 8)
            if all(row["expected_usd_estimate"] is not None for row in missing) else None,
            "history_covered_epochs": sum(row["expected_usd_estimate"] is not None for row in missing),
            "cost_note": "Worst case uses configured prices and remaining attempts. The player limit can overshoot by an in-flight call. Expected cost estimates one attempt from recorded spend; null means incomplete history."}
