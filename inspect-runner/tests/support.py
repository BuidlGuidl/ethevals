from ethevals.actors import player, grader
from ethevals.checks import check_player, check_grader
from ethevals.runner import build_task as actor_task


def build_task(evaluation, config, key, mode, answer, epochs):
    actor = check_player(evaluation, answer) if answer else player(config, key, mode)
    grade = check_grader() if answer else grader(config)
    return actor_task(evaluation, config, actor, grade, mode, epochs)
