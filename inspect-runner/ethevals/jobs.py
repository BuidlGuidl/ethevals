"""Plan missing trials and run them through Harbor."""
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
from typing import Any, Literal

from harbor.models.task.task import Task
from pydantic import Field, model_validator

from .config import Declaration, parse_file
from .files import content_hash
from .harbor_tasks import lint_task
from .skills import SkillsPack, pack_skills
from .trial_rows import fold_rows, recover_rows, write_rows


class ModelSettings(Declaration):
    name: str
    effort: str | None = None
    kwargs: dict[str, Any] = Field(default_factory=dict)


class AgentSettings(Declaration):
    name: str
    version: str = Field(min_length=1, pattern=r"^\d+\.\d+\.\d+[^\s]*$")
    model: str
    paid_by: Literal["plan", "api_key", "free"]
    cost_limit_usd: float = Field(ge=0, allow_inf_nan=False)
    modes: list[Literal["vanilla", "internet", "skills"]] = Field(default_factory=lambda: ["internet"])
    kwargs: dict[str, Any] = Field(default_factory=dict)


class JobSettings(Declaration):
    harbor_version: str
    time_limit: int = Field(gt=0)
    trials: int = Field(default=3, gt=0)
    max_attempts: int = Field(default=2, gt=0)
    modes: list[Literal["vanilla", "internet", "skills"]]
    models: dict[str, ModelSettings]
    agents: dict[str, AgentSettings]

    @model_validator(mode="after")
    def check_references(self):
        for key, agent in self.agents.items():
            if agent.model not in self.models:
                raise ValueError(f"agents.{key}.model: unknown model {agent.model!r}")
            if {"version", "model_name", "reasoning_effort"} & agent.kwargs.keys():
                raise ValueError(f"agents.{key}: set version, model, and effort outside kwargs")
        for key, model in self.models.items():
            if {"version", "model_name", "reasoning_effort"} & model.kwargs.keys():
                raise ValueError(f"models.{key}: set version, model, and effort outside kwargs")
        return self


def load_job(path: Path | None = None) -> JobSettings:
    config = parse_file(JobSettings, path or Path(__file__).with_name("job.yaml"))
    if config.harbor_version != version("harbor"):
        raise ValueError(f"Job requires Harbor {config.harbor_version}; installed version is {version('harbor')}")
    return config


def task_entry(path: Path) -> dict:
    lint_task(path)
    task = Task(path)
    metadata = task.config.metadata
    pillar = metadata.get("pillar")
    if pillar not in {"concepts", "transactions", "building", "security"}:
        raise ValueError(f"{path}: metadata.pillar must name a board pillar")
    modes = metadata.get("modes")
    if not isinstance(modes, list) or not modes or any(not isinstance(mode, str) or mode not in {"vanilla", "internet", "skills"} for mode in modes):
        raise ValueError(f"{path}: metadata.modes must list supported modes")
    motivation = metadata.get("motivation")
    if not isinstance(motivation, str) or not motivation.strip():
        raise ValueError(f"{path}: metadata.motivation must be a nonempty line")
    files = {file.relative_to(path).as_posix(): file.read_bytes() for file in path.rglob("*")
             if file.is_file() and not {".DS_Store", "__pycache__", ".pytest_cache"}.intersection(file.parts)}
    return {"id": f"{pillar}/{path.name}", "hash": content_hash(files), "pillar": pillar,
            "motivation": motivation, "instruction": (path / "instruction.md").read_text(), "modes": modes}


def write_catalog(paths: list[Path], output: Path) -> None:
    entries = [task_entry(path) for path in paths]
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Task IDs must be unique")
    output.mkdir(parents=True, exist_ok=True)
    (output / "catalog.json").write_text(json.dumps({"tasks": entries, "skills_hash": pack_skills().hash}, indent=2) + "\n")


def plan(paths: list[Path], config: JobSettings, previous: list[dict], *, agents=None,
         models=None, modes=None, trials=None, trial=None, retry_errors=False,
         skills_pack: SkillsPack | None = None) -> dict:
    from .trial_rows import trial_identity

    modes = modes or config.modes
    if set(modes) - set(config.modes):
        raise ValueError("Selected modes must be listed in the job config")
    if "skills" in modes and skills_pack is None:
        skills_pack = pack_skills()
    for selected, available, label in [(agents, config.agents, "agent"), (models, config.models, "model")]:
        if selected and set(selected) - available.keys():
            raise ValueError(f"Unknown {label}: {', '.join(sorted(set(selected) - available.keys()))}")
    prior = {trial_identity(row): row for row in previous}
    missing, exhausted, selected = [], [], []
    ids = set()
    combinations = 0
    for path in paths:
        task = task_entry(path)
        if task["id"] in ids:
            raise ValueError(f"Duplicate task ID: {task['id']}")
        ids.add(task["id"])
        for key, agent in config.agents.items():
            if agents and key not in agents or models and agent.model not in models:
                continue
            model = config.models[agent.model]
            for mode in modes:
                if mode not in task["modes"] or mode not in agent.modes:
                    continue
                combinations += 1
                for number in [trial] if trial is not None else range(1, (trials or config.trials) + 1):
                    metadata = {"task_id": task["id"], "task_hash": task["hash"],
                                "skills_hash": skills_pack.hash if mode == "skills" else None,
                                "agent": None if mode == "vanilla" else agent.name, "model": model.name, "effort": model.effort,
                                "mode": mode, "trial": number}
                    identity = trial_identity(metadata)
                    if identity in selected:
                        raise ValueError("Selected agent settings produce duplicate trial identities")
                    selected.append(identity)
                    row = prior.get(identity, {})
                    attempt = row.get("attempt", 0)
                    if row.get("status") in {"passed", "failed"}:
                        continue
                    if attempt >= config.max_attempts and not retry_errors:
                        exhausted.append(row)
                        continue
                    reserve = agent.cost_limit_usd if agent.paid_by == "api_key" else 0.0
                    remaining = max(1, config.max_attempts - attempt)
                    missing.append({**metadata, "task_path": str(path.resolve()), "agent_key": key,
                                    "agent_version": agent.version, "harbor_version": config.harbor_version,
                                    "paid_by": agent.paid_by, "time_limit": config.time_limit,
                                    "attempt": attempt + 1, "remaining_attempts": remaining,
                                    "agent_reserve_usd": reserve, "judge_reserve_usd": 0.0,
                                    "worst_case_usd": reserve * remaining})
    if not selected:
        raise ValueError("No tasks declare a selected mode and agent")
    if trial is not None and combinations != 1:
        raise ValueError("--trial requires exactly one task, agent, and mode")
    return {"missing": missing, "missing_trials": len(missing), "exhausted_errors": exhausted,
            "worst_case_usd": round(sum(row["worst_case_usd"] for row in missing), 8), "selected": selected}


def budget_check(report: dict, budget: float | None, *, required=False) -> dict:
    if budget is not None and (not math.isfinite(budget) or budget < 0):
        raise ValueError("Budget must be a finite, nonnegative USD amount")
    if required and report["missing"] and budget is None:
        raise ValueError("An agent trial requires --budget before Harbor starts")
    report.update(budget_usd=budget, within_budget=budget is None or report["worst_case_usd"] <= budget)
    return report


async def run(report: dict, config: JobSettings, output: Path, previous: list[dict], *,
              skills_pack: SkillsPack | None = None) -> bool:
    from harbor.job import Job
    from harbor.models.job.config import JobConfig
    from .trial_rows import trial_identity

    if not report["within_budget"]:
        raise ValueError("Budget exceeded; no trials started")
    skills_path = None
    if any(item["mode"] == "skills" for item in report["missing"]):
        skills_pack = skills_pack if skills_pack is not None else pack_skills()
        if any(item["skills_hash"] != skills_pack.hash for item in report["missing"] if item["mode"] == "skills"):
            raise ValueError("The skills pack differs from the plan; plan the trials again")
        skills_path = (output / "skills" / skills_pack.hash).resolve()
        for name, data in skills_pack.files.items():
            path = skills_path / name.removeprefix("/skills/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    for item in report["missing"]:
        path = Path(item["task_path"])
        missing = [name for name in Task(path).config.metadata.get("required_env", []) if not os.environ.get(name)]
        if missing:
            raise ValueError(f"{path}: missing {', '.join(missing)}")
        if (path / "tests/criteria.md").exists() and item["paid_by"] != "free":
            raise ValueError(f"{path}: criteria require the judge runner before agent trials can start")
    try:
        for item in report["missing"]:
            agent = config.agents[item["agent_key"]]
            model = config.models[agent.model]
            kwargs = {**model.kwargs, **agent.kwargs, "version": agent.version}
            if model.effort is not None:
                kwargs["reasoning_effort"] = model.effort
            harbor = {"name": agent.name, "model_name": model.name, "kwargs": kwargs,
                      "override_timeout_sec": config.time_limit}
            if item["mode"] == "skills":
                harbor["skills"] = [str(skills_path)]
            name = hashlib.sha256(json.dumps([item, harbor], sort_keys=True).encode()).hexdigest()[:24]
            destination = output / "jobs" / name
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "board.json").write_text(json.dumps(item, indent=2) + "\n")
            job = await Job.create(JobConfig(
                job_name=name, jobs_dir=output / "jobs", n_concurrent_trials=1, quiet=True,
                agents=[harbor], tasks=[{"path": item["task_path"]}],
                verifier={"override_timeout_sec": config.time_limit}, environment={"type": "docker"},
            ))
            await job.run()
            write_rows(output / "rows.jsonl", fold_rows(previous, recover_rows(output)))
    finally:
        rows = fold_rows(previous, recover_rows(output))
        write_rows(output / "rows.jsonl", rows)
    selected = {tuple(identity) for identity in report["selected"]}
    observed = {trial_identity(row): row for row in rows if trial_identity(row) in selected}
    return len(observed) == len(selected) and all(row["status"] != "error" for row in observed.values())
