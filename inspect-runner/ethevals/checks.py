"""Key-free agents use the production task and scoring path."""
from dataclasses import dataclass

from inspect_ai.model import ModelOutput, ModelInfo, ModelCost, get_model, set_model_info
from inspect_ai.solver import solver
from inspect_ai.util import sandbox

from .config import uses_sandbox
from .actors import Actor, Grader, quiz_solver
from .scorers import target_reference
from .check_script import run_solution


@dataclass
class CheckRun:
    solver: object
    reply: str = ""


def quiz_check_solver(evaluation, answer):
    replies = {
        "reference": target_reference(evaluation.target, evaluation.declaration),
        "empty": "",
    }
    return CheckRun(quiz_solver(evaluation), replies[answer])


@solver
def solution(evaluation, answer):
    async def solve(state, generate):
        if answer == "reference":
            await run_solution(evaluation, sandbox())
        return await generate(state)
    return solve


CHECK_SOLVERS = {"quiz": quiz_check_solver, "build": lambda evaluation, answer: CheckRun(solution(evaluation, answer)),
                 "act": lambda evaluation, answer: CheckRun(solution(evaluation, answer))}
CHECK_MODES = {"quiz": "vanilla", "build": "internet", "act": "internet"}


def check_agent(evaluation, answer, mode=None):
    set_model_info("mockllm/model", ModelInfo(cost=ModelCost(input=0, output=0, input_cache_read=0, input_cache_write=0)))
    if evaluation.declaration.type not in CHECK_SOLVERS:
        raise ValueError(f"type {evaluation.declaration.type!r} has no reference check solver")
    check = CHECK_SOLVERS[evaluation.declaration.type](evaluation, answer)

    def reply(messages, tools, tool_choice, config):
        return ModelOutput.from_content("mockllm/model", check.reply)

    return Actor(get_model("mockllm/model", custom_outputs=reply), {
        "model": "mockllm/model", "harness": None, "harness_version": None,
        "effort": None, "prices": {}, "cost_source": "mock",
    }, lambda evaluation: check.solver, lambda evaluation: uses_sandbox(mode or CHECK_MODES[evaluation.declaration.type]), True)


def check_grader():
    return Grader(get_model("mockllm/model"), {
        "grader_model": "mockllm/model", "grader_effort": None, "grader_prices": {}, "grader_cost_source": "mock",
    })
