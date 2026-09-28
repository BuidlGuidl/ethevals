import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import anyio
from inspect_ai import Task, eval, task_with
from inspect_ai.model import GenerateConfig, ModelOutput, get_model
from inspect_ai.solver import Solver, generate, multiple_choice, solver
from inspect_ai.util import SandboxEnvironmentSpec, sandbox

from .config import Config, register_prices
from .loader import Eval, eval_files
from .rows import epoch_identity, export_rows, store_rows
from .scorers import SCORERS, named_checks
from .sandboxes import compose_file
from .agents import internet_solver


def quiz_solver(evaluation: Eval) -> Solver:
    return multiple_choice() if evaluation.declaration.choices else generate()


@dataclass
class CheckRun:
    solver: Solver
    reply: str = ""


def quiz_check_solver(evaluation: Eval, answer: str) -> CheckRun:
    content = "\n".join(SCORERS[item.kind].reference(item, evaluation.declaration) for item in evaluation.scorers)
    content = content if answer == "reference" else "" if answer == "empty" else "Default output from mockllm/model"
    return CheckRun(quiz_solver(evaluation), content)


@solver
def build_workspace(evaluation: Eval, answer: str) -> Solver:
    async def solve(state, generate):
        if answer == "reference":
            root = evaluation.folder / "scorer/solution"
            for path in eval_files(root):
                await sandbox().write_file(f"/workspace/{path.relative_to(root)}", path.read_bytes())
        # Keep mock usage visible in the same log and row path as quiz checks.
        return await generate(state)
    return solve


def build_check_solver(evaluation: Eval, answer: str) -> CheckRun:
    return CheckRun(build_workspace(evaluation, answer))


# Build checks can copy scorer/solution/ or leave workspace untouched here.
# Both cases still use the same task, scorers, logs, and results exporter.
CHECK_SOLVERS: dict[str, Callable[[Eval, str], CheckRun]] = {
    "quiz": quiz_check_solver, "build": build_check_solver,
}
CHECK_MODES = {"quiz": "vanilla", "scenario": "internet", "build": "internet", "act": "internet"}


@solver
def mock_delay(seconds: float) -> Solver:
    async def solve(state, generate):
        await anyio.sleep(seconds)
        return state
    return solve


def build_task(evaluation: Eval, config: Config, model_key: str | None, mode: str,
               answer: str | None, epochs: int, delay: float = 0) -> Task:
    if mode == "skills":
        raise ValueError("The skills mode is not implemented yet")
    if mode not in evaluation.declaration.modes:
        raise ValueError(f"{evaluation.folder / 'eval.yaml'}: modes: {mode!r} is not declared")
    if answer:
        if evaluation.declaration.type not in CHECK_SOLVERS:
            raise ValueError(f"type {evaluation.declaration.type!r} has no reference check solver")
        check = CHECK_SOLVERS[evaluation.declaration.type](evaluation, answer)
        solve = check.solver
        # The script is identified by answer_kind and eval_hash in the task
        # name. Do not put outputs with random message IDs in model arguments.
        def reply(messages, tools, tool_choice, config):
            return ModelOutput.from_content("mockllm/model", check.reply)

        model = get_model("mockllm/model", custom_outputs=reply)
        effort, prices, cost_source = None, {}, "mock"
    else:
        if mode == "vanilla" and evaluation.declaration.type != "quiz":
            raise ValueError("The vanilla mode supports only quiz evals")
        item = config.models[model_key]
        effort, prices, cost_source = item.effort, item.prices.model_dump(), f"computed:{item.price_source}"
        model = get_model(item.model, config=GenerateConfig(reasoning_effort=effort))
        solve = quiz_solver(evaluation) if mode == "vanilla" else internet_solver(item.harness, config, effort)
    sample = evaluation.sample()
    # A plain call has no sandbox and receives only the prompt and choices.
    if mode == "vanilla" or (answer and evaluation.declaration.type == "quiz"):
        sample.files = None
    else:
        sample.sandbox = SandboxEnvironmentSpec(type="docker", config=str(compose_file(evaluation.folder, evaluation.declaration.type)))
    metadata = {**sample.metadata, "created_at": datetime.now(timezone.utc).isoformat(),
                "model": str(model), "effort": effort,
                "harness": config.models[model_key].harness if mode == "internet" and not answer else None,
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
        scorer=named_checks([item.model_dump() for item in evaluation.scorers], str(evaluation.folder), free_check=bool(answer)),
        model=model, epochs=epochs,
        time_limit=evaluation.declaration.time_limit or config.time_limits.get(evaluation.declaration.type, config.time_limit),
        token_limit=config.token_limit, metadata=metadata,
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
            max_samples=config.max_samples, max_tasks=config.max_tasks, log_buffer=1, display="plain",
        )
    rows = [row for row in export_rows(output) if epoch_identity(row, row["epoch"]) in selected]
    return len(rows) == len(selected) and all(row["status"] != "error" for row in rows), rows
