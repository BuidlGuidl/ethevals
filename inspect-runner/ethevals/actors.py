from dataclasses import dataclass
from typing import Callable, get_args

from inspect_ai.model import GenerateConfig, Model, ModelInfo, ModelCost, get_model, get_model_info, set_model_info
from inspect_ai.solver import SolverSpec
from inspect_ai._eval.loader import solver_from_spec

from .agents import HARNESSES, CodexModel, internet_solver, CHOICE_TEMPLATE
from .config import Mode, GraderConfig, uses_sandbox


def quiz_solver_spec(evaluation):
    return SolverSpec(solver="multiple_choice", args={"template": CHOICE_TEMPLATE}) if evaluation.declaration.choices else SolverSpec(solver="generate")


def quiz_solver(evaluation):
    spec = quiz_solver_spec(evaluation)
    return solver_from_spec(spec)


@dataclass
class Actor:
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


def actor(config, key, mode, item, agent=None, planning=False):
    model, metadata = (None, actor_metadata(item, config)) if planning else model_actor(item, config)
    harness = agent.harness if agent else None
    if harness == "codex_cli" and not planning:
        model = CodexModel(model)
    metadata.update(harness=harness, harness_version=HARNESSES[harness].version if harness else None)
    metadata["search"] = agent.search if agent and config.search else None

    def solve(evaluation):
        if mode == "vanilla":
            return quiz_solver(evaluation)
        return internet_solver(config, agent, evaluation.skills if mode == "skills" else None)

    return Actor(model, metadata, solve, lambda evaluation: uses_sandbox(mode), key=key)


def grader(config):
    return Grader(*model_actor(config.grader, config, "grader_"))


def select_actors(config, *, models=None, agents=None, modes=None, answer=None, planning=False):
    from .checks import check_mode, check_agent, check_grader
    if unknown := set(agents or []) - config.agents.keys():
        raise ValueError(f"Unknown agent names: {', '.join(sorted(unknown))}")
    if unknown := set(models or []) - config.models.keys():
        raise ValueError(f"Unknown model names: {', '.join(sorted(unknown))}")
    if modes and set(modes) - set(get_args(Mode)):
        raise ValueError(f"Unknown modes: {modes}")
    selected_modes = list(dict.fromkeys(modes or (["vanilla"] if models and not agents else
                          ["internet", "skills"] if agents and not models else get_args(Mode))))
    if modes and agents and not any(uses_sandbox(mode) for mode in selected_modes):
        raise ValueError("--agents requires an internet or skills mode")
    if modes and models and "vanilla" not in selected_modes:
        raise ValueError("--models requires the vanilla mode")
    if answer:
        grade = check_grader()

        def agents_for(evaluation):
            if set(evaluation.scorer_kinds) == {"rubric"}:
                return []
            declared = evaluation.declaration.modes
            default = check_mode(evaluation)
            selected = modes or [default if default in declared else declared[0]]
            return [(mode, check_agent(evaluation, answer, mode=mode))
                    for mode in dict.fromkeys(evaluation.declaration.modes) if mode in selected]
    else:
        grade = None if planning else grader(config)
        actors = []
        for mode in selected_modes:
            for key in (agents or config.agents) if uses_sandbox(mode) else (models or config.models):
                agent = config.agents[key] if uses_sandbox(mode) else None
                actors.append((mode, actor(config, key, mode, config.models[agent.model if agent else key], agent, planning)))

        def agents_for(evaluation):
            return [(mode, actor) for mode, actor in actors if mode in evaluation.declaration.modes]
    return agents_for, grade
