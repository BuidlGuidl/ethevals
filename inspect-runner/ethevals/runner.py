import hashlib
import json
from pathlib import Path
from typing import Callable

import anyio
from inspect_ai import Task, eval_set
from inspect_ai.model import GenerateConfig, ModelOutput, get_model
from inspect_ai.solver import Solver, generate, multiple_choice, solver

from .config import Config, register_prices
from .loader import Eval
from .rows import export_rows
from .scorers import named_checks


def quiz_solver(evaluation: Eval) -> Solver:
    return multiple_choice() if evaluation.declaration.choices else generate()


def quiz_check_solver(evaluation: Eval, answer: str) -> Solver:
    return quiz_solver(evaluation)


# Build checks can copy scorer/solution/ or leave workspace untouched here.
# Both cases still use the same task, scorers, logs, and results exporter.
CHECK_SOLVERS: dict[str, Callable[[Eval, str], Solver]] = {"quiz": quiz_check_solver}


@solver
def mock_delay(seconds: float) -> Solver:
    async def solve(state, generate):
        await anyio.sleep(seconds)
        return state
    return solve


def build_task(evaluation: Eval, config: Config, model_key: str | None, mode: str,
               answer: str | None, epochs: int, delay: float = 0) -> Task:
    if mode != config.modes.plain:
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
        content = content if answer == "reference" else "" if answer == "empty" else "Default output from mockllm/model"
        # The script is identified by answer_kind and eval_hash in the task
        # name. Do not put outputs with random message IDs in model arguments.
        def reply(messages, tools, tool_choice, config):
            return ModelOutput.from_content("mockllm/model", content)

        model = get_model("mockllm/model", custom_outputs=reply)
        effort, prices, cost_source = None, {}, "mock"
    else:
        if evaluation.declaration.type != "quiz":
            raise ValueError("The plain mode supports only quiz evals")
        item = config.models[model_key]
        effort, prices, cost_source = item.effort, item.prices.model_dump(), f"computed:{item.price_source}"
        model = get_model(item.model, config=GenerateConfig(reasoning_effort=effort))
        solve = quiz_solver(evaluation)
    sample = evaluation.sample()
    # A plain call has no sandbox and receives only the prompt and choices.
    if evaluation.declaration.type == "quiz":
        sample.files = None
    metadata = {**sample.metadata, "model": str(model), "effort": effort, "harness": None,
                "mode": mode, "answer_kind": answer, "prices": prices, "cost_source": cost_source,
                "grader_model": "mockllm/model" if answer else config.models[config.grader].model,
                "grader_effort": None if answer else config.models[config.grader].effort,
                "grader_prices": {} if answer else config.models[config.grader].prices.model_dump()}
    identity = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:16]
    return Task(
        name=f"{evaluation.id.replace('/', '-')}-{identity}",
        version=evaluation.hash, dataset=[sample],
        solver=[mock_delay(delay), solve] if delay else solve,
        scorer=named_checks(evaluation.scorer.kind, evaluation.scorer.model_dump()),
        model=model, epochs=epochs, time_limit=config.time_limit, metadata=metadata,
    )


def run(evals: list[Eval], config: Config, output: Path, *, models: list[str] | None = None,
        modes: list[str] | None = None, answer: str | None = None,
        epochs: int | None = None, delay: float = 0) -> tuple[bool, list[dict]]:
    register_prices(config)
    selected_models = [None] if answer else models or list(config.models)
    selected_modes = modes or [config.modes.plain]
    tasks = [build_task(evaluation, config, model, mode, answer, epochs or config.epochs, delay)
             for evaluation in evals for model in selected_models for mode in selected_modes]
    grader = get_model("mockllm/model") if answer else get_model(
        config.models[config.grader].model,
        config=GenerateConfig(reasoning_effort=config.models[config.grader].effort),
    )
    success, logs = eval_set(
        tasks, log_dir=str(output / "logs"), model_roles={"grader": grader},
        retry_attempts=1, retry_on_error=0, fail_on_error=False,
        max_samples=1, max_tasks=1, log_buffer=1, display="plain",
    )
    rows = export_rows(logs, output / "rows.jsonl")
    return success and all(row["status"] != "error" for row in rows), rows
