"""Key-free players use the production task and scoring path."""
from dataclasses import dataclass

import anyio
from inspect_ai.model import ModelOutput, ModelInfo, ModelCost, get_model, set_model_info
from inspect_ai.solver import solver
from inspect_ai.util import sandbox

from .actors import Player, Grader, quiz_solver
from .scorers import SCORERS
from .check_script import run_solution


@dataclass
class CheckRun:
    solver: object
    reply: str = ""


def quiz_check_solver(evaluation, answer):
    replies = {
        "reference": "\n".join(SCORERS[item.kind].reference(item, evaluation.declaration) for item in evaluation.scorers),
        "empty": "", "default": "Default output from mockllm/model",
    }
    return CheckRun(quiz_solver(evaluation), replies[answer])


@solver
def build_workspace(evaluation, answer):
    async def solve(state, generate):
        if answer == "reference":
            for name, data in evaluation.files.items():
                if name.startswith("scorer/solution/"):
                    await sandbox().write_file("/workspace/" + name.removeprefix("scorer/solution/"), data)
        return await generate(state)
    return solve


@solver
def act_solution(evaluation, answer):
    async def solve(state, generate):
        if answer == "reference":
            await run_solution(evaluation)
        return await generate(state)
    return solve


CHECK_SOLVERS = {"quiz": quiz_check_solver, "build": lambda evaluation, answer: CheckRun(build_workspace(evaluation, answer)),
                 "act": lambda evaluation, answer: CheckRun(act_solution(evaluation, answer))}
CHECK_MODES = {"quiz": "vanilla", "scenario": "internet", "build": "internet", "act": "internet"}


@solver
def mock_delay(seconds):
    async def solve(state, generate):
        await anyio.sleep(seconds)
        return state
    return solve


def check_player(evaluation, answer, delay=0, mode=None):
    set_model_info("mockllm/model", ModelInfo(cost=ModelCost(input=0, output=0, input_cache_read=0, input_cache_write=0)))
    if evaluation.declaration.type not in CHECK_SOLVERS:
        raise ValueError(f"type {evaluation.declaration.type!r} has no reference check solver")
    check = CHECK_SOLVERS[evaluation.declaration.type](evaluation, answer)

    def reply(messages, tools, tool_choice, config):
        return ModelOutput.from_content("mockllm/model", check.reply)

    solve = [mock_delay(delay), check.solver] if delay else check.solver
    return Player(get_model("mockllm/model", custom_outputs=reply), {
        "model": "mockllm/model", "harness": None, "harness_version": None,
        "effort": None, "prices": {}, "cost_source": "mock", "answer_kind": answer,
    }, lambda evaluation: solve, lambda evaluation: (mode or CHECK_MODES[evaluation.declaration.type]) != "vanilla", True)


def check_grader():
    return Grader(get_model("mockllm/model"), {
        "grader_model": "mockllm/model", "grader_effort": None, "grader_prices": {}, "grader_cost_source": "mock",
    })
