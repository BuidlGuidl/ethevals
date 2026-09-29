from dataclasses import dataclass
from typing import Callable, get_args

from inspect_ai.model import GenerateConfig, Model, ModelInfo, ModelCost, get_model, get_model_info, set_model_info
from inspect_ai.solver import SolverSpec
from inspect_ai._eval.loader import solver_from_spec

from .agents import AGENTS, CodexModel, internet_solver
from .config import Mode, GraderConfig, uses_sandbox


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
    key: str | None = None


@dataclass
class Grader:
    model: Model
    metadata: dict


def actor_metadata(item, config, prefix=""):
    return {prefix + key: value for key, value in {
        "model": item.model, "effort": item.effort, "prices": config.prices[item.model].model_dump(),
        "cost_source": "computed:guess",
    }.items()}


def model_actor(item, config, prefix=""):
    info = get_model_info(item.model) or ModelInfo()
    set_model_info(item.model, info.model_copy(update={"cost": ModelCost(**config.prices[item.model].model_dump())}))
    model = get_model(item.model, config=GenerateConfig(reasoning_effort=item.effort,
                                                       max_tokens=item.max_tokens if isinstance(item, GraderConfig) else None))
    return model, actor_metadata(item, config, prefix)


def player(config, key, mode, planning=False):
    item = config.agents[key]
    if planning:
        model, metadata = None, actor_metadata(item, config)
    else:
        model, metadata = model_actor(item, config)
    harness = item.harness if mode == "internet" else None
    if harness == "codex_cli" and not planning:
        model = CodexModel(model)
    metadata.update(harness=harness, harness_version=AGENTS[harness].version if harness else None)

    def solve(evaluation):
        if mode == "vanilla":
            if evaluation.declaration.type != "quiz":
                raise ValueError("The vanilla mode supports only quiz evals")
            return quiz_solver(evaluation)
        return internet_solver(harness, config, item)

    return Player(model, metadata, solve, lambda evaluation: uses_sandbox(mode), key=key)


def grader(config):
    model, metadata = model_actor(config.grader, config, "grader_")
    return Grader(model, metadata)


def select_actors(config, agents=None, modes=None, answer=None, *, planning=False):
    from .checks import CHECK_MODES, check_player, check_grader
    if unknown := set(agents or []) - config.agents.keys():
        raise ValueError(f"Unknown agent names: {', '.join(sorted(unknown))}")
    if modes and set(modes) - set(get_args(Mode)):
        raise ValueError(f"Unknown modes: {modes}")
    if answer:
        grade = check_grader()

        def players(evaluation):
            selected = modes or [CHECK_MODES[evaluation.declaration.type]]
            return [(mode, check_player(evaluation, answer, mode=mode))
                    for mode in dict.fromkeys(evaluation.declaration.modes) if mode in selected]
    else:
        grade = None if planning else grader(config)
        actors = [(mode, player(config, key, mode, planning)) for mode in dict.fromkeys(modes or ["vanilla"])
                  for key in agents or config.agents]

        def players(evaluation):
            return [(mode, actor) for mode, actor in actors if mode in evaluation.declaration.modes]
    return players, grade
