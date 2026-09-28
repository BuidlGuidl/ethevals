import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai import Task, eval, task_with
from inspect_ai.util import SandboxEnvironmentSpec

from .actors import Player, Grader
from .config import Config, read_yaml
from .loader import Eval
from .rows import epoch_identity, export_rows, store_rows
from .scorers import named_checks, EVALUATIONS, SCORERS, check_names, rubric_budget, scoring_seconds, SCORING_OVERHEAD_SECONDS
from .sandboxes import compose_file
from .preparation import prepare_eval, prepare_compose, sandbox_type
from .images.tag import image_inputs, image_tag


def build_task(evaluation: Eval, config: Config, player: Player, grader: Grader,
               mode: str, epochs: int, compose: Path | None = None) -> Task:
    if mode == "skills":
        raise ValueError("The skills mode is not implemented yet")
    if mode not in evaluation.declaration.modes:
        raise ValueError(f"{evaluation.folder / 'eval.yaml'}: modes: {mode!r} is not declared")
    sample = evaluation.sample()
    images = {}
    if player.sandbox_for(evaluation):
        compose = compose or compose_file(evaluation.declaration.type)
        sample.sandbox = SandboxEnvironmentSpec(type=sandbox_type(evaluation), config=str(compose))
        images = {name: service["image"] for name, service in read_yaml(compose)["services"].items()}
    else:
        sample.files = None
    working_limit = evaluation.declaration.time_limit or config.time_limits.get(evaluation.declaration.type, config.time_limit)
    time_limit = working_limit * 3
    scoring_limit = scoring_seconds(evaluation) + SCORING_OVERHEAD_SECONDS
    if scoring_seconds(evaluation) and scoring_limit >= time_limit / 2:
        raise ValueError(f"Scoring needs {scoring_limit} seconds, but Inspect allows {time_limit / 2}.")
    metadata = {**sample.metadata, **player.metadata, **grader.metadata,
                "created_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
                "images": images,
                "runner_inputs": image_inputs() if images else {},
                "chain_inputs": image_inputs(image="chain") if images.get("chain") == image_tag(image="chain") else {},
                "cost_limit_usd": config.cost_limit,
                "grader_cost_limit_usd": rubric_budget(evaluation, config), "max_attempts": config.max_attempts,
                "free_check": player.free_check,
                "working_limit_seconds": working_limit, "time_limit_seconds": time_limit,
                "scoring_limit_seconds": scoring_limit,
                "check_names": check_names(evaluation, player.free_check)}
    sample.metadata = dict(metadata)
    if any(SCORERS[item.kind].discover and item.kind not in evaluation.discovered_checks for item in evaluation.scorers):
        raise ValueError("Discover reference checks with prepare_eval before building a task.")
    EVALUATIONS[(evaluation.id, evaluation.hash)] = evaluation
    identity = hashlib.sha256(json.dumps(epoch_identity(metadata, 0)).encode()).hexdigest()[:16]
    return Task(
        name=f"{evaluation.id.replace('/', '-')}-{identity}",
        version=evaluation.hash, dataset=[sample], solver=player.solver_for(evaluation),
        scorer=named_checks(evaluation.id, evaluation.hash),
        model=player.model, epochs=epochs,
        working_limit=working_limit, time_limit=time_limit,
        cost_limit=config.cost_limit, metadata=metadata,
    )


def run(evals: list[Eval], config: Config, output: Path, *, players, grade: Grader,
        epochs: int | None = None, fresh: bool = False, retry_errors: bool = False) -> tuple[bool, list[dict]]:
    previous = {epoch_identity(row, row["epoch"]): row for row in store_rows(output)}
    tasks, selected, discovery_errors = [], set(), []
    for evaluation in evals:
        actors = players(evaluation)
        if not actors:
            continue
        pending = []
        for mode, actor in actors:
            for epoch in range(1, (epochs or config.epochs) + 1):
                identity = epoch_identity({"eval_id": evaluation.id, "eval_hash": evaluation.hash,
                                           **actor.metadata, "mode": mode}, epoch)
                selected.add(identity)
                prior = previous.get(identity, {})
                if fresh or (prior.get("status") not in {"passed", "failed"}
                             and (prior.get("attempt", 0) < config.max_attempts or retry_errors)):
                    pending.append((mode, actor, epoch, prior.get("attempt", 0) + 1))
        if not pending:
            continue
        try:
            compose = prepare_compose(evaluation, output)
            evaluation = prepare_eval(evaluation, output, compose)
        except (ValueError, RuntimeError) as error:
            discovery_errors.append({"eval_id": evaluation.id, "eval_hash": evaluation.hash, "error": str(error)})
            logging.getLogger(__name__).error("%s: check discovery failed: %s", evaluation.id, error)
            continue
        for mode, actor, epoch, attempt in pending:
            task = build_task(evaluation, config, actor, grade, mode, 1, compose)
            task.metadata.update(epoch=epoch, attempt=attempt)
            tasks.append(task_with(task, name=f"{task.name}-epoch-{epoch}"))
    if not selected:
        raise ValueError("No evals declare a selected mode")
    output.mkdir(parents=True, exist_ok=True)
    error_path = output / "discovery-errors.json"
    if discovery_errors:
        previous_errors = json.loads(error_path.read_text()) if error_path.exists() else []
        error_path.write_text(json.dumps(previous_errors + discovery_errors, indent=2) + "\n")
    if tasks:
        eval(tasks, log_dir=str(output / "logs"), model_roles={"grader": grade.model},
             retry_on_error=0, fail_on_error=False, max_samples=config.max_samples,
             max_tasks=config.max_tasks, log_buffer=1, display="plain")
    rows = [row for row in export_rows(output) if epoch_identity(row, row["epoch"]) in selected]
    return not discovery_errors and len(rows) == len(selected) and all(row["status"] != "error" for row in rows), rows
