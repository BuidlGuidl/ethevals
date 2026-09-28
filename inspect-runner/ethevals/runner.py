import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai import Task, eval, task_with
from inspect_ai.util import SandboxEnvironmentSpec

from .actors import Player, Grader
from .config import Config, read_yaml
from .loader import Eval
from .rows import epoch_identity, export_rows, store_rows
from .scorers import named_checks, EVALUATIONS, check_names, rubric_budget
from .sandboxes import compose_file
from .preparation import prepare_eval, prepare_compose


def build_task(evaluation: Eval, config: Config, player: Player, grader: Grader,
               mode: str, epochs: int, compose: Path | None = None) -> Task:
    if mode == "skills":
        raise ValueError("The skills mode is not implemented yet")
    if mode not in evaluation.declaration.modes:
        raise ValueError(f"{evaluation.folder / 'eval.yaml'}: modes: {mode!r} is not declared")
    sample = evaluation.sample()
    images = {}
    if player.sandbox_for(evaluation):
        compose = compose or compose_file()
        sample.sandbox = SandboxEnvironmentSpec(type="docker", config=str(compose))
        images = {name: service["image"] for name, service in read_yaml(compose)["services"].items()}
    else:
        sample.files = None
    metadata = {**sample.metadata, **player.metadata, **grader.metadata,
                "created_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
                "images": images, "cost_limit_usd": config.cost_limit,
                "grader_cost_limit_usd": rubric_budget(evaluation, config), "max_attempts": config.max_attempts,
                "grader_max_tokens": config.grader.max_tokens, "free_check": player.free_check,
                "check_names": check_names(evaluation, player.free_check)}
    sample.metadata = dict(metadata)
    if any(item.kind == "tests" for item in evaluation.scorers) and not evaluation.test_checks:
        raise ValueError("Discover reference checks with prepare_eval before building a task.")
    EVALUATIONS[(evaluation.id, evaluation.hash)] = evaluation
    identity = hashlib.sha256(json.dumps(epoch_identity(metadata, 0)).encode()).hexdigest()[:16]
    return Task(
        name=f"{evaluation.id.replace('/', '-')}-{identity}",
        version=evaluation.hash, dataset=[sample], solver=player.solver_for(evaluation),
        scorer=named_checks(evaluation.id, evaluation.hash),
        model=player.model, epochs=epochs,
        time_limit=evaluation.declaration.time_limit or config.time_limits.get(evaluation.declaration.type, config.time_limit),
        cost_limit=config.cost_limit, metadata=metadata,
    )


def run(evals: list[Eval], config: Config, output: Path, *, players, grade: Grader,
        epochs: int | None = None, fresh: bool = False, retry_errors: bool = False) -> tuple[bool, list[dict]]:
    previous = {epoch_identity(row, row["epoch"]): row for row in store_rows(output)}
    tasks, selected = [], set()
    for evaluation in evals:
        actors = players(evaluation)
        if not actors:
            continue
        compose = prepare_compose(evaluation, output)
        evaluation = prepare_eval(evaluation, output, compose)
        for mode, actor in actors:
            for epoch in range(1, (epochs or config.epochs) + 1):
                task = build_task(evaluation, config, actor, grade, mode, 1, compose)
                task.metadata["epoch"] = epoch
                task = task_with(task, name=f"{task.name}-epoch-{epoch}")
                identity = epoch_identity(task.metadata, epoch)
                selected.add(identity)
                prior = previous.get(identity, {})
                if fresh or (prior.get("status") not in {"passed", "failed"}
                             and (prior.get("attempt", 0) < config.max_attempts or retry_errors)):
                    task.metadata["attempt"] = prior.get("attempt", 0) + 1
                    tasks.append(task)
    if not selected:
        raise ValueError("No evals declare a selected mode")
    if tasks:
        eval(tasks, log_dir=str(output / "logs"), model_roles={"grader": grade.model},
             retry_on_error=0, fail_on_error=False, max_samples=config.max_samples,
             max_tasks=config.max_tasks, log_buffer=1, display="plain")
    rows = [row for row in export_rows(output) if epoch_identity(row, row["epoch"]) in selected]
    return len(rows) == len(selected) and all(row["status"] != "error" for row in rows), rows
