"""Select epochs once for both the budget plan and the runner."""
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import NamedTuple

from .rows import epoch_identity
from .scorers import rubric_budget, scoring_seconds, SCORING_OVERHEAD_SECONDS, SCORERS
from .preparation import SETUP_SECONDS, STARTUP_SECONDS, CLEANUP_SECONDS, TASK_LIFECYCLE_SECONDS, WORKSPACE_COPY_SECONDS


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


def budget_check(report, budget, *, required=False):
    if budget is None and required and report["missing"]:
        raise ValueError("A paid run requires --budget before any provider is built")
    if budget is not None and (not math.isfinite(budget) or budget < 0):
        raise ValueError("Budget must be a finite, nonnegative USD amount")
    report.update(budget_usd=budget, within_budget=budget is None or report["worst_case_usd"] <= budget)
    return report


def epoch_seconds(evaluation, config, actor):
    working = evaluation.declaration.time_limit or config.time_limits.get(evaluation.declaration.type, config.time_limit)
    seconds = 3 * working + scoring_seconds(evaluation) + SCORING_OVERHEAD_SECONDS
    if actor.sandbox_for(evaluation):
        seconds += STARTUP_SECONDS + CLEANUP_SECONDS + WORKSPACE_COPY_SECONDS
        if any(SCORERS[item.kind].setup for item in evaluation.scorers):
            seconds += SETUP_SECONDS
    return seconds


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


def plan(evals, config, players, previous, *, epochs=None, retry_errors=False, fresh=False, wall_seconds=None,
         selection=None, preparation_seconds=0):
    if wall_seconds is not None and (not math.isfinite(wall_seconds) or wall_seconds <= 0):
        raise ValueError("Wall seconds must be finite and positive")
    selection = selection or epoch_selection(evals, config, players, previous, epochs, fresh, retry_errors)
    _, pending, exhausted = selection
    missing, deferred, admitted, total, longest, reserved = [], [], [], 0, 0, preparation_seconds
    lifecycle = 0
    concurrency = min(config.max_tasks, config.max_samples)
    groups = defaultdict(list)
    for item in pending:
        groups[item.evaluation.id, item.mode, item.epoch].append(item)
    rows = {}
    for item in pending:
        evaluation, mode, actor, epoch, attempt = item
        metadata = {"eval_id": evaluation.id, "eval_hash": evaluation.hash, "type": evaluation.declaration.type,
                    **actor.metadata, "mode": mode, "epoch": epoch}
        # Reserve every remaining runner attempt. Runtime spends one per invocation.
        remaining = max(1, config.max_attempts - attempt + 1)
        per_attempt = config.cost_limit + rubric_budget(evaluation, config)
        if mode == "internet" and config.search_provider:
            per_attempt += config.search_limit * config.search_price_usd
        history = [row["model_cost_usd"] + row["grader_cost_usd"] for row in previous
                   if all(row.get(key) == metadata.get(key) for key in ("type", "model", "harness", "effort", "mode", "answer_kind"))
                   and row.get("model_cost_usd") is not None and row.get("grader_cost_usd") is not None]
        seconds = epoch_seconds(evaluation, config, actor)
        row = {**metadata, "attempt": attempt, "remaining_attempts": remaining,
                        "wall_seconds": seconds,
                        "per_attempt_usd": per_attempt, "worst_case_usd": per_attempt * remaining,
                        "expected_usd_estimate": sum(history) / len(history) if history else None}
        rows[id(item)] = row
    queue = sorted(groups.values(), key=lambda group: sum(rows[id(item)]["wall_seconds"] for item in group))
    compositions = set()
    for group in queue:
        group_rows = [rows[id(item)] for item in group]
        seconds = sum(row["wall_seconds"] for row in group_rows)
        group_longest = max(row["wall_seconds"] for row in group_rows)
        # prepare_compose writes one immutable path per eval hash.
        compose_files = {item.evaluation.hash for item in group if item.actor.sandbox_for(item.evaluation)}
        task_overhead = 2 * TASK_LIFECYCLE_SECONDS * len(compose_files - compositions)
        # Task initialization and final cleanup can run outside the sample dispatcher.
        bound = (preparation_seconds + lifecycle + task_overhead
                 + (total + seconds) / concurrency + (1 - 1 / concurrency) * max(longest, group_longest))
        if wall_seconds is not None and bound > wall_seconds:
            deferred.extend(group_rows)
        else:
            missing.extend(group_rows)
            admitted.extend(group)
            compositions.update(compose_files)
            total += seconds
            longest = max(longest, group_longest)
            lifecycle += task_overhead
            reserved = bound
    return Plan({"missing": missing, "missing_epochs": len(missing),
            "cheapest_group_usd": min((sum(rows[id(item)]["worst_case_usd"] for item in group) for group in queue), default=0),
            "deferred": deferred, "deferred_epochs": len(deferred), "wall_seconds": wall_seconds,
            "reserved_wall_seconds": reserved,
            "preparation_seconds": preparation_seconds, "concurrency": concurrency,
            "task_lifecycle_seconds": lifecycle,
            "exhausted_errors": exhausted,
            "worst_case_usd": round(sum(row["worst_case_usd"] for row in missing), 8),
            "expected_usd_estimate": round(sum(row["expected_usd_estimate"] for row in missing), 8)
            if all(row["expected_usd_estimate"] is not None for row in missing) else None,
            "history_covered_epochs": sum(row["expected_usd_estimate"] is not None for row in missing),
            "cost_note": "Worst case includes configured model, grader, and search prices for remaining attempts. The player limit can overshoot by an in-flight call. Expected cost covers one attempt's model and grader spend only; null means incomplete history."}, admitted)
