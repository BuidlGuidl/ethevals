import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai import Task, eval, task_with
from inspect_ai.util import SandboxEnvironmentSpec

from .actors import Actor, Grader, select_actors
from .config import Config, read_yaml, uses_sandbox
from .loader import Eval
from .rows import epoch_identity, export_rows, previous_rows
from .planning import plan, budget_check
from .scorers import EVALUATIONS, SCORERS, rubric_budget, rubric_questions, GRADER_CALLS, GRADER_CONFIG, FORGE_SECONDS
from .check_script import CHECK_SECONDS
from .preparation import build_images, prepare_compose, check_capacity
from .images.tag import image_inputs, image_tag

SCORING_OVERHEAD_SECONDS = 120


def task_limits(evaluation, config):
    working_limit = config.time_limits[evaluation.declaration.type]
    questions = len(rubric_questions(evaluation.files)) if "rubric" in evaluation.scorer_kinds else 0
    scoring_seconds = ((FORGE_SECONDS if "tests" in evaluation.scorer_kinds else 0)
                       + (CHECK_SECONDS if "check_script" in evaluation.scorer_kinds else 0)
                       + questions * GRADER_CALLS * GRADER_CONFIG.timeout)
    scoring_limit = scoring_seconds + SCORING_OVERHEAD_SECONDS
    time_limit = max(3 * working_limit, 2 * scoring_limit)
    return working_limit, time_limit, scoring_limit


def build_task(evaluation: Eval, config: Config, agent: Actor, grader: Grader,
               mode: str, epochs: int, compose: Path | None) -> Task:
    if mode not in evaluation.declaration.modes:
        raise ValueError(f"{evaluation.folder / 'eval.yaml'}: modes: {mode!r} is not declared")
    sample = evaluation.sample()
    images = {}
    if agent.sandbox_for(evaluation):
        services = read_yaml(compose)["services"]
        sample.sandbox = SandboxEnvironmentSpec(type="ethevals_docker", config=str(compose))
        images = {name: service["image"] for name, service in services.items()}
    else:
        sample.files = None
    working_limit, time_limit, scoring_limit = task_limits(evaluation, config)
    metadata = {**sample.metadata, **agent.metadata, **grader.metadata,
                "created_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
                "images": images,
                "runner_inputs": image_inputs() if images else {},
                "chain_inputs": image_inputs(image="chain") if images.get("chain") == image_tag(image="chain") else {},
                "cost_limit_usd": config.cost_limit,
                "grader_cost_limit_usd": rubric_budget(evaluation, config), "max_attempts": config.max_attempts,
                "search_limit": config.search_limit if uses_sandbox(mode) and config.search else 0,
                "working_limit_seconds": working_limit, "time_limit_seconds": time_limit,
                "scoring_limit_seconds": scoring_limit}
    sample.metadata = dict(metadata)
    EVALUATIONS[(evaluation.id, evaluation.hash)] = evaluation
    identity = hashlib.sha256(json.dumps(epoch_identity(metadata, 0)).encode()).hexdigest()[:16]
    return Task(
        name=f"{evaluation.id.replace('/', '-')}-{identity}",
        version=evaluation.hash, dataset=[sample], solver=agent.solver_for(evaluation),
        scorer=[SCORERS[kind](evaluation.id, evaluation.hash)
                for kind in evaluation.scorer_kinds if not (agent.free_check and kind == "rubric")],
        model=agent.model, epochs=epochs,
        working_limit=working_limit, time_limit=time_limit,
        cost_limit=config.cost_limit, metadata=metadata,
    )


def run(evals: list[Eval], config: Config, output: Path, *,
        epochs: int | None = None, fresh: bool = False, retry_errors: bool = False,
        rows_file: Path | None = None, agents=None, models=None, modes=None, answer=None,
        budget=None) -> tuple[bool, list[dict]]:
    previous = previous_rows(output, rows_file)
    agents_for, _ = select_actors(config, agents=agents, modes=modes, answer=answer, models=models, planning=True)
    initial = plan(evals, config, agents_for, previous, epochs=epochs, fresh=fresh, retry_errors=retry_errors)
    report = budget_check(initial.report, budget, required=not answer)
    output.mkdir(parents=True, exist_ok=True)
    (output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["within_budget"]:
        raise ValueError("Budget exceeded. No agent or grader ran.")
    if not answer and initial.pending:
        providers = {actor.metadata["model"].split("/", 1)[0] for evaluation in evals for _, actor in agents_for(evaluation)}
        providers.add(config.grader.model.split("/", 1)[0])
        missing = sorted(key for provider, key in {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
                         "openrouter": "OPENROUTER_API_KEY"}.items() if provider in providers and not os.environ.get(key))
        if missing:
            raise ValueError(f"Missing provider keys for paid epochs: {', '.join(missing)}")
    prepared, preparation_errors = {}, []
    if any(item.actor.sandbox_for(item.evaluation) for item in initial.pending):
        check_capacity(config, [item.evaluation for item in initial.pending if item.actor.sandbox_for(item.evaluation)])
        build_images()
    for evaluation in evals:
        work = [item for item in initial.pending if item.evaluation.id == evaluation.id]
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
        agents_for, grade = select_actors(config, agents=agents, modes=modes, answer=answer, models=models)
        actors = {evaluation.id: {(mode, actor.key): actor for mode, actor in agents_for(evaluation)}
                  for evaluation in evals}
        for original, mode, planned_actor, epoch, attempt in initial.pending:
            if original.id not in prepared:
                continue
            evaluation, compose = prepared[original.id]
            actor = actors[original.id][mode, planned_actor.key]
            task = build_task(evaluation, config, actor, grade, mode, 1, compose)
            task.metadata.update(epoch=epoch, attempt=attempt)
            tasks.append(task_with(task, name=f"{task.name}-epoch-{epoch}"))
    error_path = output / "preparation-errors.json"
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
    pending = {epoch_identity(row, row["epoch"]): row["attempt"] for row in report["missing"]}
    actual = {epoch_identity(row, row["epoch"]): row for row in rows}
    return (not preparation_errors and pending.keys() <= actual.keys()
            and all(actual[key]["status"] != "error" and actual[key]["attempt"] == attempt
                    for key, attempt in pending.items())), rows
