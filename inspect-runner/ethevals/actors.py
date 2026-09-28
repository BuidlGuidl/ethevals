from dataclasses import dataclass
from typing import Callable

from inspect_ai.model import GenerateConfig, Model, ModelInfo, ModelCost, get_model, get_model_info, set_model_info
from inspect_ai.solver import generate, multiple_choice

from .agents import HARNESS_VERSIONS, internet_solver


def quiz_solver(evaluation):
    return multiple_choice() if evaluation.declaration.choices else generate()


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
    model = get_model(item.model, config=GenerateConfig(reasoning_effort=item.effort))
    return model, {prefix + key: value for key, value in {
        "model": str(model), "effort": item.effort, "prices": item.prices.model_dump(),
        "cost_source": f"computed:{item.price_source}",
    }.items()}


def player(config, key, mode):
    item = config.models[key]
    model, metadata = model_actor(item)
    harness = item.harness if mode == "internet" else None
    metadata.update(harness=harness, harness_version=HARNESS_VERSIONS.get(harness), answer_kind=None)

    def solve(evaluation):
        if mode == "vanilla":
            if evaluation.declaration.type != "quiz":
                raise ValueError("The vanilla mode supports only quiz evals")
            return quiz_solver(evaluation)
        return internet_solver(harness, config, item)

    return Player(model, metadata, solve, lambda evaluation: mode != "vanilla")


def grader(config):
    model, metadata = model_actor(config.models[config.grader], "grader_")
    return Grader(model, metadata)
