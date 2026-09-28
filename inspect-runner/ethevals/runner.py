import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import anyio
from inspect_ai import Task, eval, task_with
from inspect_ai.model import GenerateConfig, ModelOutput, get_model
from inspect_ai.solver import Solver, generate, multiple_choice, solver

from .config import Config, register_prices
from .loader import Eval
from .rows import epoch_identity, export_rows, store_rows
from .scorers import named_checks


def quiz_solver(evaluation: Eval) -> Solver:
    return multiple_choice() if evaluation.declaration.choices else generate()


def quiz_check_solver(evaluation: Eval, answer: str) -> Solver:
    return quiz_solver(evaluation)


# Build checks can copy scorer/solution/ or leave workspace untouched here.
# Both cases still use the same task, scorers, logs, and results exporter.
CHECK_SOLVERS: dict[str, Callable[[Eval, str], Solver]] = {"quiz": quiz_check_solver}
CHECK_MODES = {"quiz": "vanilla", "scenario": "internet", "build": "internet", "act": "internet"}


@solver
def mock_delay(seconds: float) -> Solver:
    async def solve(state, generate):
        await anyio.sleep(seconds)
        return state
    return solve


def build_task(evaluation: Eval, config: Config, model_key: str | None, mode: str,
               answer: str | None, epochs: int, delay: float = 0) -> Task:
    if mode != "vanilla" and not answer:
        raise ValueError(f"mode {mode!r} needs the agent runner from step 2b")
    if mode not in evaluation.declaration.modes:
        raise ValueError(f"{evaluation.folder / 'eval.yaml'}: modes: {mode!r} is not declared")
    if answer:
        if evaluation.declaration.type not in CHECK_SOLVERS:
            raise ValueError(f"type {evaluation.declaration.type!r} has no reference check solver")
        solve = CHECK_SOLVERS[evaluation.declaration.type](evaluation, answer)
        target = getattr(evaluation.scorer, "target", "")
        target = target[0] if isinstance(target, list) else target
        content = f"ANSWER: {target}" if evaluation.declaration.choices else target
        if getattr(evaluation.scorer, "reference", None) is not None:
            content = evaluation.scorer.reference
        content = content if answer == "reference" else "" if answer == "empty" else "Default output from mockllm/model"
        # The script is identified by answer_kind and eval_hash in the task
        # name. Do not put outputs with random message IDs in model arguments.
        def reply(messages, tools, tool_choice, config):
            return ModelOutput.from_content("mockllm/model", content)

        model = get_model("mockllm/model", custom_outputs=reply)
        effort, prices, cost_source = None, {}, "mock"
    else:
        if evaluation.declaration.type != "quiz":
            raise ValueError("The vanilla mode supports only quiz evals")
        item = config.models[model_key]
        effort, prices, cost_source = item.effort, item.prices.model_dump(), f"computed:{item.price_source}"
        model = get_model(item.model, config=GenerateConfig(reasoning_effort=effort))
        solve = quiz_solver(evaluation)
    sample = evaluation.sample()
    # A plain call has no sandbox and receives only the prompt and choices.
    if evaluation.declaration.type == "quiz":
        sample.files = None
    metadata = {**sample.metadata, "created_at": datetime.now(timezone.utc).isoformat(),
                "model": str(model), "effort": effort, "harness": None,
                "mode": mode, "answer_kind": answer, "prices": prices, "cost_source": cost_source,
                "grader_model": "mockllm/model" if answer else config.models[config.grader].model,
                "grader_effort": None if answer else config.models[config.grader].effort,
                "grader_cost_source": "mock" if answer else f"computed:{config.models[config.grader].price_source}",
                "grader_prices": {} if answer else config.models[config.grader].prices.model_dump()}
    identity = hashlib.sha256(json.dumps(epoch_identity(metadata, 0)).encode()).hexdigest()[:16]
    return Task(
        name=f"{evaluation.id.replace('/', '-')}-{identity}",
        version=evaluation.hash, dataset=[sample],
        solver=[mock_delay(delay), solve] if delay else solve,
        scorer=named_checks(evaluation.scorer.kind, evaluation.scorer.model_dump()),
        model=model, epochs=epochs, time_limit=config.time_limit, metadata=metadata,
    )


def run(evals: list[Eval], config: Config, output: Path, *, models: list[str] | None = None,
        modes: list[str] | None = None, answer: str | None = None,
        epochs: int | None = None, delay: float = 0, fresh: bool = False) -> tuple[bool, list[dict]]:
    register_prices(config)
    selected_models = [None] if answer else models or list(config.models)
    if modes and set(modes) - {"vanilla", "internet", "skills"}:
        raise ValueError(f"Unknown modes: {modes}")
    previous = {epoch_identity(row, row["epoch"]): row for row in store_rows(output)}
    tasks, selected = [], set()
    for evaluation in evals:
        selected_modes = modes or ([CHECK_MODES[evaluation.declaration.type]] if answer else ["vanilla"])
        for mode in dict.fromkeys(evaluation.declaration.modes):
            if mode not in selected_modes:
                continue
            for model in selected_models:
                for epoch in range(1, (epochs or config.epochs) + 1):
                    task = build_task(evaluation, config, model, mode, answer, 1, delay)
                    task.metadata["epoch"] = epoch
                    task = task_with(task, name=f"{task.name}-epoch-{epoch}")
                    identity = epoch_identity(task.metadata, epoch)
                    selected.add(identity)
                    if fresh or previous.get(identity, {}).get("status") not in {"passed", "failed"}:
                        tasks.append(task)
    if not selected:
        raise ValueError("No evals declare a selected mode")
    grader = get_model("mockllm/model") if answer else get_model(
        config.models[config.grader].model,
        config=GenerateConfig(reasoning_effort=config.models[config.grader].effort),
    )
    if tasks:
        # One Inspect task per epoch lets our identity select missing work even
        # when Inspect's own key changes with the grader or execution config.
        eval(
            tasks, log_dir=str(output / "logs"), model_roles={"grader": grader},
            retry_on_error=0, fail_on_error=False,
            max_samples=1, max_tasks=1, log_buffer=1, display="plain",
        )
    rows = [row for row in export_rows(output) if epoch_identity(row, row["epoch"]) in selected]
    return len(rows) == len(selected) and all(row["status"] != "error" for row in rows), rows
