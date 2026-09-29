from ethevals.actors import player, grader
from ethevals.checks import check_player, check_grader
from ethevals.runner import build_task as actor_task
from ethevals.runner import run as actor_run


def build_task(evaluation, config, key, mode, answer, epochs, compose=None):
    actor = check_player(evaluation, answer, mode=mode) if answer else player(config, key, mode)
    grade = check_grader() if answer else grader(config)
    return actor_task(evaluation, config, actor, grade, mode, epochs, compose)


def run(evals, config, output, *, models=None, modes=None, answer=None, delay=0, **kwargs):
    return actor_run(evals, config, output, models=models, modes=modes, answer=answer, delay=delay, **kwargs)
