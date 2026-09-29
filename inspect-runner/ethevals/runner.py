import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai import Task, eval, task_with
from inspect_ai.util import SandboxEnvironmentSpec

from .actors import Player, Grader, select_actors
from .config import Config, read_yaml
from .loader import Eval
from .rows import epoch_identity, export_rows, previous_rows
from .planning import plan, budget_check
from .scorers import EVALUATIONS, SCORERS, rubric_budget, rubric_questions, GRADER_CALLS, GRADER_CONFIG, FORGE_SECONDS
from .check_script import CHECK_SECONDS
from .sandboxes import compose_file
from .preparation import prepare_compose, check_capacity
from .images.tag import image_inputs, image_tag

SCORING_OVERHEAD_SECONDS = 120


def task_limits(evaluation, config):
    working_limit = config.time_limits[evaluation.declaration.type]
    time_limit = working_limit * 3
    questions = len(rubric_questions(evaluation.files)) if "rubric" in evaluation.scorer_kinds else 0
    scoring_seconds = ((FORGE_SECONDS if "tests" in evaluation.scorer_kinds else 0)
                       + (CHECK_SECONDS if "check_script" in evaluation.scorer_kinds else 0)
                       + questions * GRADER_CALLS * GRADER_CONFIG.timeout)
    scoring_limit = scoring_seconds + SCORING_OVERHEAD_SECONDS
    if scoring_seconds and scoring_limit >= time_limit / 2:
        raise ValueError(f"Scoring needs {scoring_limit} seconds, but Inspect allows {time_limit / 2}.")
    return working_limit, time_limit, scoring_limit


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
        sample.sandbox = SandboxEnvironmentSpec(type="ethevals_docker", config=str(compose))
        images = {name: service["image"] for name, service in read_yaml(compose)["services"].items()}
        limit = read_yaml(compose)["services"]["default"]["mem_limit"]
        sample.input += f"\nYour container has a {limit} memory limit, shared by the CLI and its tools. Exceeding it can end the epoch with an error.\n"
    else:
        sample.files = None
    working_limit, time_limit, scoring_limit = task_limits(evaluation, config)
    metadata = {**sample.metadata, **player.metadata, **grader.metadata,
                "created_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
                "images": images,
                "runner_inputs": image_inputs() if images else {},
                "chain_inputs": image_inputs(image="chain") if images.get("chain") == image_tag(image="chain") else {},
                "cost_limit_usd": config.cost_limit,
                "grader_cost_limit_usd": rubric_budget(evaluation, config), "max_attempts": config.max_attempts,
                "search_limit": config.search_limit if mode == "internet" and config.search else 0,
                "search_price_usd": config.search_price_usd,
                "working_limit_seconds": working_limit, "time_limit_seconds": time_limit,
                "scoring_limit_seconds": scoring_limit}
    sample.metadata = dict(metadata)
    EVALUATIONS[(evaluation.id, evaluation.hash)] = evaluation
    identity = hashlib.sha256(json.dumps(epoch_identity(metadata, 0)).encode()).hexdigest()[:16]
    return Task(
        name=f"{evaluation.id.replace('/', '-')}-{identity}",
        version=evaluation.hash, dataset=[sample], solver=player.solver_for(evaluation),
        scorer=[SCORERS[kind](evaluation.id, evaluation.hash)
                for kind in evaluation.scorer_kinds if not (player.free_check and kind == "rubric")],
        model=player.model, epochs=epochs,
        working_limit=working_limit, time_limit=time_limit,
        cost_limit=config.cost_limit, metadata=metadata,
    )


def run(evals: list[Eval], config: Config, output: Path, *,
        epochs: int | None = None, fresh: bool = False, retry_errors: bool = False,
        rows_file: Path | None = None, agents=None, modes=None, answer=None,
        budget=None, wall_seconds=None) -> tuple[bool, list[dict]]:
    previous = previous_rows(output, rows_file)
    players, _ = select_actors(config, agents, modes, answer, planning=True)
    initial = plan(evals, config, players, previous, wall_seconds=wall_seconds,
                   epochs=epochs, fresh=fresh, retry_errors=retry_errors)
    report = budget_check(initial.report, budget, required=not answer)
    output.mkdir(parents=True, exist_ok=True)
    (output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["within_budget"]:
        raise ValueError("Budget exceeded. No player or grader ran.")
    if not answer and initial.admitted and not os.environ.get("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is required for missing paid epochs")
    prepared, preparation_errors = {}, []
    if any(item.actor.sandbox_for(item.evaluation) for item in initial.admitted):
        check_capacity(config)
    for evaluation in evals:
        work = [item for item in initial.admitted if item.evaluation.id == evaluation.id]
        if not work:
            continue
        try:
            compose = prepare_compose(evaluation, output) if any(item.actor.sandbox_for(evaluation) for item in work) else None
            prepared[evaluation.id] = (evaluation, compose)
        except (ValueError, RuntimeError) as error:
            preparation_errors.append({"eval_id": evaluation.id, "eval_hash": evaluation.hash, "error": str(error)})
            logging.getLogger(__name__).error("%s: container preparation failed: %s", evaluation.id, error)
    tasks = []
    if prepared:
        players, grade = select_actors(config, agents, modes, answer)
        actors = {evaluation.id: {(mode, actor.key): actor for mode, actor in players(evaluation)}
                  for evaluation in evals}
        for original, mode, planned_actor, epoch, attempt in initial.admitted:
            if original.id not in prepared:
                continue
            evaluation, compose = prepared[original.id]
            actor = actors[original.id][mode, planned_actor.key]
            task = build_task(evaluation, config, actor, grade, mode, 1, compose)
            task.metadata.update(epoch=epoch, attempt=attempt)
            tasks.append(task_with(task, name=f"{task.name}-epoch-{epoch}"))
    error_path = output / "discovery-errors.json"
    if preparation_errors:
        previous_errors = json.loads(error_path.read_text()) if error_path.exists() else []
        error_path.write_text(json.dumps(previous_errors + preparation_errors, indent=2) + "\n")
    try:
        if tasks:
            concurrency = config.concurrency
            eval(tasks, log_dir=str(output / "logs"), model_roles={"grader": grade.model},
                 retry_on_error=0, fail_on_error=False, max_samples=concurrency,
                 max_tasks=concurrency, max_sandboxes=concurrency, log_buffer=1, display="plain")
    finally:
        rows = [row for row in export_rows(output, previous) if epoch_identity(row, row["epoch"]) in initial.selected]
    admitted = {epoch_identity(row, row["epoch"]): row["attempt"] for row in report["missing"]}
    actual = {epoch_identity(row, row["epoch"]): row for row in rows}
    return (not preparation_errors and admitted.keys() <= actual.keys()
            and all(actual[key]["status"] != "error" and actual[key]["attempt"] == attempt
                    for key, attempt in admitted.items())), rows
