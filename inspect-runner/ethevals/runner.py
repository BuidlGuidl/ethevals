import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai import Task, eval, task_with
from inspect_ai.util import SandboxEnvironmentSpec

from .actors import Player, Grader, player, grader
from .config import Config, register_prices, read_yaml
from .loader import Eval
from .rows import epoch_identity, export_rows, store_rows
from .scorers import named_checks
from .sandboxes import IMAGES, compose_file
from .files import inline_file


def build_task(evaluation: Eval, config: Config, player: Player, grader: Grader,
               mode: str, epochs: int, compose: Path | None = None) -> Task:
    if mode == "skills":
        raise ValueError("The skills mode is not implemented yet")
    if mode not in evaluation.declaration.modes:
        raise ValueError(f"{evaluation.folder / 'eval.yaml'}: modes: {mode!r} is not declared")
    sample = evaluation.sample()
    images = {}
    if player.sandbox_for(evaluation):
        compose = compose or compose_file(evaluation.folder, evaluation.declaration.type)
        sample.sandbox = SandboxEnvironmentSpec(type="docker", config=str(compose))
        images = {name: service["image"] for name, service in read_yaml(compose)["services"].items()}
        sample.files["/workspace/foundry.toml"] = inline_file((IMAGES / "foundry.toml").read_bytes())
        sample.input += "\nGrading uses the supplied foundry.toml. Changes to compiler settings or remappings do not affect grading. OpenZeppelin and forge-std come from the image. Other Solidity dependencies must use relative imports under src/ or lib/."
    else:
        sample.files = None
    metadata = {**sample.metadata, **player.metadata, **grader.metadata,
                "created_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
                "images": images, "cost_limit_usd": config.cost_limit,
                "grader_cost_limit_usd": config.grader_cost_limit, "max_attempts": config.max_attempts}
    identity = hashlib.sha256(json.dumps(epoch_identity(metadata, 0)).encode()).hexdigest()[:16]
    return Task(
        name=f"{evaluation.id.replace('/', '-')}-{identity}",
        version=evaluation.hash, dataset=[sample], solver=player.solver_for(evaluation),
        scorer=named_checks([item.model_dump() for item in evaluation.scorers], str(evaluation.folder),
                            free_check=player.free_check,
                            files={name: base64.b64encode(data).decode() for name, data in evaluation.files.items()},
                            grader_cost_limit=config.grader_cost_limit),
        model=player.model, epochs=epochs,
        time_limit=evaluation.declaration.time_limit or config.time_limits.get(evaluation.declaration.type, config.time_limit),
        cost_limit=config.cost_limit, metadata=metadata,
    )


def run(evals: list[Eval], config: Config, output: Path, *, models: list[str] | None = None,
        modes: list[str] | None = None, answer: str | None = None,
        epochs: int | None = None, delay: float = 0, fresh: bool = False) -> tuple[bool, list[dict]]:
    from .checks import CHECK_MODES, check_player, check_grader
    register_prices(config)
    grade = check_grader() if answer else grader(config)
    selected_models = [None] if answer else models or list(config.models)
    if modes and set(modes) - {"vanilla", "internet", "skills"}:
        raise ValueError(f"Unknown modes: {modes}")
    previous = {epoch_identity(row, row["epoch"]): row for row in store_rows(output)}
    tasks, selected = [], set()
    for evaluation in evals:
        selected_modes = modes or ([CHECK_MODES[evaluation.declaration.type]] if answer else ["vanilla"])
        compose = None
        if "compose.yaml" in evaluation.files:
            compose = output.resolve() / "inputs" / evaluation.hash / "compose.yaml"
            compose.parent.mkdir(parents=True, exist_ok=True)
            compose.write_bytes(evaluation.files["compose.yaml"])
        for mode in dict.fromkeys(evaluation.declaration.modes):
            if mode not in selected_modes:
                continue
            for model in selected_models:
                actor = check_player(evaluation, answer, delay) if answer else player(config, model, mode)
                for epoch in range(1, (epochs or config.epochs) + 1):
                    task = build_task(evaluation, config, actor, grade, mode, 1, compose)
                    task.metadata["epoch"] = epoch
                    task = task_with(task, name=f"{task.name}-epoch-{epoch}")
                    identity = epoch_identity(task.metadata, epoch)
                    selected.add(identity)
                    prior = previous.get(identity, {})
                    if fresh or (prior.get("status") not in {"passed", "failed"}
                                 and prior.get("attempt", 0) < config.max_attempts):
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
