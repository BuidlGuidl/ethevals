"""Select missing epochs and reserve their budget."""
import math
from dataclasses import dataclass
from typing import NamedTuple

from .rows import epoch_identity
from .scorers import rubric_budget


class Epoch(NamedTuple):
    evaluation: object
    mode: str
    actor: object
    epoch: int
    attempt: int


@dataclass
class Plan:
    report: dict
    pending: list[Epoch]
    selected: set


def budget_check(report, budget, *, required=False):
    if budget is None and required and report["missing"]:
        raise ValueError("A paid run requires --budget before any provider is built")
    if budget is not None and (not math.isfinite(budget) or budget < 0):
        raise ValueError("Budget must be a finite, nonnegative USD amount")
    report.update(budget_usd=budget, within_budget=budget is None or report["worst_case_usd"] <= budget)
    return report


def epoch_selection(evals, config, agents_for, previous, epochs=None, fresh=False, retry_errors=False, epoch=None):
    prior = {epoch_identity(row, row["epoch"]): row for row in previous}
    selected, pending, exhausted = set(), [], []
    combinations = 0
    for evaluation in evals:
        for mode, actor in agents_for(evaluation):
            combinations += 1
            for number in [epoch] if epoch is not None else range(1, (epochs or config.epochs) + 1):
                identity = epoch_identity({"eval_id": evaluation.id, "eval_hash": evaluation.hash,
                                           **actor.metadata, "mode": mode,
                                           "skills_hash": evaluation.skills_hash if mode == "skills" else None}, number)
                selected.add(identity)
                row = prior.get(identity, {})
                attempt = row.get("attempt", 0)
                if fresh or (row.get("status") not in {"passed", "failed"}
                             and (attempt < config.max_attempts or retry_errors)):
                    pending.append(Epoch(evaluation, mode, actor, number, attempt + 1))
                elif row.get("status") == "error":
                    exhausted.append(row)
    if not selected:
        raise ValueError("No evals declare a selected mode")
    if epoch is not None and combinations != 1:
        raise ValueError("--epoch requires exactly one eval, actor, and mode")
    return selected, pending, exhausted


def plan(evals, config, agents_for, previous, *, epochs=None, retry_errors=False, fresh=False, epoch=None):
    selected, pending, exhausted = epoch_selection(evals, config, agents_for, previous, epochs, fresh, retry_errors, epoch)
    missing = []
    for item in pending:
        evaluation, mode, actor, epoch, attempt = item
        # Reserve every remaining runner attempt. Runtime spends one per invocation.
        remaining = max(1, config.max_attempts - attempt + 1)
        per_attempt = config.cost_limit + rubric_budget(evaluation, config)
        row = {"eval_id": evaluation.id, "eval_hash": evaluation.hash,
               "skills_hash": evaluation.skills_hash if mode == "skills" else None,
               **actor.metadata, "actor_key": actor.key, "mode": mode, "epoch": epoch, "attempt": attempt,
               "remaining_attempts": remaining,
               "per_attempt_usd": per_attempt, "worst_case_usd": per_attempt * remaining}
        missing.append(row)
    return Plan({"missing": missing, "missing_epochs": len(missing),
                 "exhausted_errors": exhausted,
                 "worst_case_usd": round(sum(row["worst_case_usd"] for row in missing), 8)}, pending, selected)
