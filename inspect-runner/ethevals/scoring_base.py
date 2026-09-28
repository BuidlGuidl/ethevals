"""Shared types for scorer kinds."""
from dataclasses import dataclass, field
from typing import Callable

from inspect_ai.scorer import Score

from .config import Declaration


def checks_score(checks):
    return Score(value="C" if all(c["passed"] for c in checks.values()) else "I", metadata={"checks": checks})


def failed_checks(names, reason):
    return {name: {"passed": False, "reason": reason} for name in names}


@dataclass
class Submission:
    captures: dict = field(default_factory=dict)


class SubmissionFailed(Exception):
    pass


@dataclass(frozen=True)
class ScorerKind:
    schema: type[Declaration]
    build: Callable
    validate: Callable
    sample_fields: Callable = lambda config: {}
    reference: Callable = lambda config, declaration: ""
    free_check: bool = True
    workspace: Callable = lambda config: ({}, "")
    names: Callable = lambda config, evaluation: []
    discover: Callable | None = None
    capture: Callable | None = None
    setup: Callable | None = None
    cache_inputs: Callable = lambda images: []
    requires: tuple[str, ...] = ()
