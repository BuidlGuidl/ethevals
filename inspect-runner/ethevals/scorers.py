import re
from dataclasses import dataclass
from typing import Callable, Literal

from inspect_ai.scorer import Score, Scorer, Target, accuracy, choice, match, pattern, scorer
from pydantic import Field, model_validator

from .config import Declaration


class TargetScorer(Declaration):
    kind: Literal["target"]
    name: str = Field(default="answer", pattern=r"^[a-z][a-z0-9_]*$")
    target: str | list[str]
    method: Literal["match", "pattern", "choice"] = "match"
    location: Literal["begin", "end", "any", "exact"] = "exact"
    ignore_case: bool = True
    numeric: bool = False
    pattern: str | None = None
    reference: str | None = None

    @model_validator(mode="after")
    def check_target(self):
        targets = [self.target] if isinstance(self.target, str) else self.target
        if not targets or any(not value.strip() for value in targets):
            raise ValueError("target must contain nonempty strings")
        if self.method == "pattern":
            if self.pattern is None:
                raise ValueError("pattern is required for method pattern")
            try:
                re.compile(self.pattern)
            except re.error as error:
                raise ValueError(f"pattern: {error}") from error
        elif self.pattern is not None:
            raise ValueError("pattern requires method pattern")
        return self


def target_scorer(config: TargetScorer) -> Scorer:
    if config.method == "choice":
        underlying = choice()
    elif config.method == "pattern":
        underlying = pattern(config.pattern, ignore_case=config.ignore_case)
    else:
        underlying = match(location=config.location, ignore_case=config.ignore_case, numeric=config.numeric)

    async def score(state, target):
        # A target list means alternatives, including for a choice quiz.
        results = [await underlying(state, Target(value)) for value in target]
        passed = any(result.value == "C" for result in results)
        reason = "Answer matches the target." if passed else "Answer does not match the target."
        if not state.output.completion.strip():
            reason = "The answer is empty."
        return Score(value="C" if passed else "I", metadata={"checks": {
            config.name: {"passed": passed, "reason": reason}
        }}, explanation=reason)

    return score


@dataclass(frozen=True)
class ScorerKind:
    schema: type[Declaration]
    build: Callable[[Declaration], Scorer]


# Step 2b adds kinds here. Each returns Score.metadata["checks"].
SCORERS: dict[str, ScorerKind] = {"target": ScorerKind(TargetScorer, target_scorer)}


@scorer(metrics=[accuracy()])
def named_checks(kind: str, declaration: dict) -> Scorer:
    entry = SCORERS[kind]
    underlying = entry.build(entry.schema.model_validate(declaration))

    async def score(state, target):
        result = await underlying(state, target)
        checks = (result.metadata or {}).get("checks")
        if not checks:
            raise ValueError(f"scorer kind {kind} returned no named checks")
        for name, check in checks.items():
            if type(check.get("passed")) is not bool or not check.get("reason", "").strip():
                raise ValueError(f"check {name} requires passed and reason")
            check["reason"] = " ".join(check["reason"].split())
        result.value = "C" if all(check["passed"] for check in checks.values()) else "I"
        return result

    return score
