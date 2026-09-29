"""Select epochs once for both the budget plan and the runner."""
import math
from dataclasses import dataclass
from typing import NamedTuple

from .rows import epoch_identity
from .scorers import rubric_budget

CONTAINER_SECONDS = 300
PREPARATION_SECONDS = 1800


class Epoch(NamedTuple):
    evaluation: object
    mode: str
    actor: object
    epoch: int
    attempt: int


@dataclass
class Plan:
    report: dict
    admitted: list[Epoch]
    selected: set


def budget_check(report, budget, *, required=False):
    if budget is None and required and report["missing"]:
        raise ValueError("A paid run requires --budget before any provider is built")
    if budget is not None and (not math.isfinite(budget) or budget < 0):
        raise ValueError("Budget must be a finite, nonnegative USD amount")
    report.update(budget_usd=budget, within_budget=budget is None or report["worst_case_usd"] <= budget)
    return report


def epoch_seconds(item, config):
    from .runner import task_limits
    _, time_limit, scoring_limit, _ = task_limits(item.evaluation, config)
    return time_limit + scoring_limit + (CONTAINER_SECONDS if item.actor.sandbox_for(item.evaluation) else 0)


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
                    pending.append(Epoch(evaluation, mode, actor, epoch, attempt + 1))
                elif row.get("status") == "error":
                    exhausted.append(row)
    if not selected:
        raise ValueError("No evals declare a selected mode")
    return selected, pending, exhausted


def plan(evals, config, players, previous, *, epochs=None, retry_errors=False, fresh=False, wall_seconds=None):
    if wall_seconds is not None and (not math.isfinite(wall_seconds) or wall_seconds <= 0):
        raise ValueError("Wall seconds must be finite and positive")
    selected, pending, exhausted = epoch_selection(evals, config, players, previous, epochs, fresh, retry_errors)
    missing, deferred, admitted = [], [], []
    reserved = PREPARATION_SECONDS if pending else 0
    for item in sorted(pending, key=lambda item: epoch_seconds(item, config)):
        evaluation, mode, actor, epoch, attempt = item
        seconds = epoch_seconds(item, config)
        if wall_seconds is not None and PREPARATION_SECONDS + seconds > wall_seconds:
            raise ValueError(f"Config error: a single epoch of {evaluation.id} needs {seconds} seconds plus "
                             f"{PREPARATION_SECONDS} seconds for preparation; --wall-seconds is {wall_seconds:g}")
        # Reserve every remaining runner attempt. Runtime spends one per invocation.
        remaining = max(1, config.max_attempts - attempt + 1)
        per_attempt = config.cost_limit + rubric_budget(evaluation, config)
        if mode == "internet" and config.search_provider:
            per_attempt += config.search_limit * config.search_price_usd
        row = {"eval_id": evaluation.id, "eval_hash": evaluation.hash, "type": evaluation.declaration.type,
               **actor.metadata, "mode": mode, "epoch": epoch, "attempt": attempt,
               "remaining_attempts": remaining, "wall_seconds": seconds,
               "per_attempt_usd": per_attempt, "worst_case_usd": per_attempt * remaining}
        if wall_seconds is not None and reserved + seconds > wall_seconds:
            deferred.append(row)
        else:
            missing.append(row)
            admitted.append(item)
            reserved += seconds
    return Plan({"missing": missing, "missing_epochs": len(missing),
                 "deferred": deferred, "deferred_epochs": len(deferred), "wall_seconds": wall_seconds,
                 "reserved_wall_seconds": reserved, "exhausted_errors": exhausted,
                 "worst_case_usd": round(sum(row["worst_case_usd"] for row in missing), 8)}, admitted, selected)
