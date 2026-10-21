"""Answer task criteria with RewardKit after Harbor saves the trial."""
import asyncio
import json
import os
from pathlib import Path
import re
from typing import Literal

from harbor.models.task.artifacts import normalize_artifact_entries, source_host_path
from harbor.models.task.task import Task
from pydantic import Field

from .config import Declaration

MAX_JUDGE_ATTEMPTS = 2

class JudgeSettings(Declaration):
    model: str = "anthropic/claude-opus-5-5"
    effort: Literal["low", "medium", "high"] = "high"
    time_limit: int = Field(default=300, gt=0)
    cost_limit_usd: float = Field(default=2.0, ge=0, allow_inf_nan=False)
    paid_by: Literal["api_key", "free"] = "api_key"
    key_env: Literal["ANTHROPIC_API_KEY"] = "ANTHROPIC_API_KEY"


def read_criteria(task: Path) -> dict[str, str]:
    path = task / "tests/criteria.md"
    if not path.exists():
        return {}
    parts = re.split(r"^##\s+(.+?)\s*$", path.read_text(), flags=re.MULTILINE)
    questions = {}
    for name, question in zip(parts[1::2], parts[2::2]):
        if name in questions or not question.strip():
            raise ValueError(f"{path}: each criteria heading must be unique and have a question")
        questions[name] = question.strip()
    if not questions:
        raise ValueError(f"{path}: write a question under each ## heading")
    return questions


def check_judge_key(settings: JudgeSettings) -> None:
    if settings.paid_by == "free":
        return
    if settings.model.startswith("anthropic/") or settings.model.startswith("claude-"):
        key = os.environ.get(settings.key_env, "")
        if not key or key.startswith("sk-ant-oat") or os.environ.get("REWARDKIT_FORCE_SUBSCRIPTION", "").strip().lower() in {"1", "true", "yes"}:
            raise ValueError(f"The judge requires {settings.key_env} and cannot use a plan token.")


async def judge_trial(folder: Path, task: Path, settings: JudgeSettings) -> None:
    from rewardkit.judges import arun_llm
    from rewardkit.models import Criterion, LLMJudge

    path = folder / "verifier/judge.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    if previous and not previous["error"]:
        return
    attempts = previous.get("attempts", int(bool(previous)))
    total_cost = previous.get("cost_usd", 0.0)
    temporary = path.with_suffix(".tmp")
    while attempts < MAX_JUDGE_ATTEMPTS:
        if attempts:
            await asyncio.sleep(2 ** attempts)
        attempts += 1
        record = {"judge": {"model": settings.model, "effort": settings.effort},
                  "paid_by": settings.paid_by, "cost_usd": 0.0 if settings.paid_by == "free" else None,
                  "attempts": attempts, "checks": {}, "error": "The judge did not finish."}
        # Count an interrupted request too, so recovery keeps the admitted limit.
        temporary.write_text(json.dumps(record, indent=2) + "\n")
        temporary.replace(path)
        cost = 0.0 if settings.paid_by == "free" else None
        try:
            questions = read_criteria(task)
            # Use provider-safe keys internally; board checks retain the task's headings.
            criteria = [Criterion(name=f"q_{index}", description=question)
                        for index, question in enumerate(questions.values())]
            files = []
            for artifact in normalize_artifact_entries(Task(task).config.artifacts):
                file = (folder / "artifacts" / artifact.destination if artifact.destination
                        else source_host_path(folder / "artifacts", artifact.source))
                if not file.resolve().is_relative_to((folder / "artifacts").resolve()):
                    raise ValueError("A judge artifact must stay inside the trial's artifacts directory.")
                if not file.exists():
                    raise ValueError(f"Missing judge artifact: {artifact.source}")
                files.append(str(file))
            trajectory = folder / "agent/trajectory.json"
            if not trajectory.is_file():
                raise ValueError("Missing judge trajectory.")
            check_judge_key(settings)
            async with asyncio.timeout(settings.time_limit):
                result = await arun_llm(LLMJudge(
                    model=settings.model, reasoning_effort=settings.effort, timeout=settings.time_limit,
                    files=tuple(files), atif_trajectory=str(trajectory)), criteria)
            record.update(output=result.output, warnings=result.warnings, usage=result.usage)
            if settings.paid_by != "free":
                cost = result.usage.get("cost_usd")
            if [score.name for score in result.scores] != [criterion.name for criterion in criteria]:
                raise ValueError("The judge did not answer every criteria question.")
            checks = {}
            for name, score in zip(questions, result.scores):
                if score.error:
                    raise ValueError(score.error)
                if type(score.raw) not in (bool, int, str) or score.raw not in (True, False, 0, 1, "yes", "no"):
                    raise ValueError(f"Criteria {name}: the judge must answer yes or no.")
                if not score.reasoning.strip():
                    raise ValueError(f"Criteria {name}: the judge must give a reason.")
                checks[name] = {"passed": score.value == 1, "reason": " ".join(score.reasoning.split())}
            record.update(checks=checks, error=None)
        except Exception as error:
            record["error"] = " ".join(str(error).split()) or type(error).__name__
        total_cost = total_cost + cost if total_cost is not None and cost is not None else None
        record["cost_usd"] = total_cost
        temporary.write_text(json.dumps(record, indent=2) + "\n")
        temporary.replace(path)
        if not record["error"]:
            return
