from ethevals.actors import player, grader, select_actors
from ethevals.checks import check_player, check_grader
from ethevals.runner import build_task as actor_task
from ethevals.runner import run as actor_run
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from ethevals.preparation import prepare_compose

INPUTS = TemporaryDirectory()


def build_task(evaluation, config, key, mode, answer, epochs, compose=None):
    if any(item.kind == "tests" for item in evaluation.scorers) and not evaluation.discovered_checks:
        evaluation = replace(evaluation, discovered_checks={"tests": ("forge:test/Token.t.sol:TokenTest:testSupply()",)})
    actor = check_player(evaluation, answer, mode=mode) if answer else player(config, key, mode)
    grade = check_grader() if answer else grader(config)
    if compose is None and actor.sandbox_for(evaluation):
        compose = prepare_compose(evaluation, Path(INPUTS.name))
    return actor_task(evaluation, config, actor, grade, mode, epochs, compose)


def run(evals, config, output, *, models=None, modes=None, answer=None, delay=0, **kwargs):
    return actor_run(evals, config, output, models=models, modes=modes, answer=answer, delay=delay, **kwargs)
