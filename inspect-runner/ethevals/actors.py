from dataclasses import dataclass
from typing import Callable, get_args

from inspect_ai.model import GenerateConfig, Model, ModelInfo, ModelCost, get_model, get_model_info, set_model_info
from inspect_ai.solver import SolverSpec
from inspect_ai._eval.loader import solver_from_spec

from .agents import AGENTS, CodexModel, internet_solver
from .config import Mode, GraderConfig


def quiz_solver_spec(evaluation):
    return SolverSpec(solver="multiple_choice" if evaluation.declaration.choices else "generate")


def quiz_solver(evaluation):
    spec = quiz_solver_spec(evaluation)
    return solver_from_spec(spec)


@dataclass
class Player:
    model: Model
    metadata: dict
    solver_for: Callable
    sandbox_for: Callable
    free_check: bool = False


@dataclass
class Grader:
    model: Model
    metadata: dict


def model_actor(item, prefix=""):
    info = get_model_info(item.model) or ModelInfo()
    set_model_info(item.model, info.model_copy(update={"cost": ModelCost(**item.prices.model_dump())}))
    model = get_model(item.model, config=GenerateConfig(reasoning_effort=item.effort,
                                                       max_tokens=item.max_tokens if isinstance(item, GraderConfig) else None))
    return model, {prefix + key: value for key, value in {
        "model": str(model), "effort": item.effort, "prices": item.prices.model_dump(),
        "cost_source": f"computed:{item.price_source}",
    }.items()}


def player(config, key, mode, planning=False):
    item = config.models[key]
    if planning:
        model, metadata = None, {"model": item.model, "effort": item.effort}
    else:
        model, metadata = model_actor(item)
    harness = item.harness if mode == "internet" else None
    if harness == "codex_cli" and not planning:
        model = CodexModel(model)
    metadata.update(harness=harness, harness_version=AGENTS[harness].version if harness else None, answer_kind=None)

    def solve(evaluation):
        if mode == "vanilla":
            if evaluation.declaration.type != "quiz":
                raise ValueError("The vanilla mode supports only quiz evals")
            return quiz_solver(evaluation)
        return internet_solver(harness, config, item)

    return Player(model, metadata, solve, lambda evaluation: mode != "vanilla")


def grader(config):
    model, metadata = model_actor(config.grader, "grader_")
    return Grader(model, metadata)


def select_actors(config, models=None, modes=None, answer=None, delay=0, *, planning=False):
    from .checks import CHECK_MODES, check_player, check_grader
    if modes and set(modes) - set(get_args(Mode)):
        raise ValueError(f"Unknown modes: {modes}")
    if answer:
        grade = check_grader()

        def players(evaluation):
            selected = modes or [CHECK_MODES[evaluation.declaration.type]]
            return [(mode, check_player(evaluation, answer, delay, mode))
                    for mode in dict.fromkeys(evaluation.declaration.modes) if mode in selected]
    else:
        grade = None if planning else grader(config)
        actors = [(mode, player(config, key, mode, planning)) for mode in dict.fromkeys(modes or ["vanilla"])
                  for key in models or config.models]

        def players(evaluation):
            return [(mode, actor) for mode, actor in actors if mode in evaluation.declaration.modes]
    return players, grade
