"""Plan missing trials and run them through Harbor."""
from contextlib import contextmanager
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.task.task import Task
from harbor.agents.factory import AgentFactory
from harbor.models.trial.config import AgentConfig
from harbor.publisher.packager import Packager
from pydantic import ValidationError

from .files import write_whole
from .job_config import JobSettings, check_credentials, check_judge_key, credential_file, load_job
from .harbor_tasks import lint_task, task_host_variables, task_judges
from .skills import SkillsPack, pack_skills
from .secret_check import check_output, remember_secrets, secret_values
from .trial_rows import fold_rows, recover_rows, trial_identity, write_rows


def task_entry(path: Path, config: JobSettings | None = None) -> dict:
    lint_task(path, config)
    task = Task(path)
    metadata = task.config.metadata
    pillar = metadata.get("pillar")
    if pillar not in {"concepts", "build", "act"}:
        raise ValueError(f"{path}: metadata.pillar must name a board pillar")
    modes = metadata.get("modes")
    if not isinstance(modes, list) or not modes or any(not isinstance(mode, str) or mode not in {"vanilla", "internet", "skills"} for mode in modes):
        raise ValueError(f"{path}: metadata.modes must list supported modes")
    digest, _ = Packager.compute_content_hash(path)
    return {"id": f"{pillar}/{path.name}", "hash": "sha256:" + digest, "pillar": pillar,
            "area": metadata.get("area"), "layer": metadata.get("layer"),
            "name": task.name, "description": task.config.task.description,
            "instruction": (path / "instruction.md").read_text(), "modes": modes}


def write_catalog(paths: list[Path], output: Path) -> None:
    entries = [task_entry(path) for path in paths]
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Task IDs must be unique")
    names = set()
    for entry in entries:
        if entry["name"] in names:
            raise ValueError(f"Duplicate task name: {entry['name']}")
        names.add(entry["name"])
    output.mkdir(parents=True, exist_ok=True)
    job = load_job()
    models = [model.name for model in job.models.values()]
    catalog = {"tasks": entries, "skills_hash": pack_skills().hash, "models": models, "n_attempts": job.n_attempts}
    (output / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")


def plan(paths: list[Path], config: JobSettings, previous: list[dict], *, agents=None,
         models=None, modes=None, n_attempts=None, trial=None,
         skills_pack: SkillsPack | None = None, retry_judge_error=False) -> dict:
    if retry_judge_error and trial is None:
        raise ValueError("--retry-judge-error requires --trial with one task, agent, and mode")
    modes = modes or config.modes
    if set(modes) - set(config.modes):
        raise ValueError("Selected modes must be listed in the job config")
    if "skills" in modes and skills_pack is None:
        skills_pack = pack_skills()
    for selected, available, label in [(agents, config.agents, "agent"), (models, config.models, "model")]:
        if selected and set(selected) - available.keys():
            raise ValueError(f"Unknown {label}: {', '.join(sorted(set(selected) - available.keys()))}")
    prior = {trial_identity(row): row for row in previous}
    missing, exhausted, selected, deferred = [], [], [], []
    ids, names = set(), set()
    combinations = 0
    for path in paths:
        task = task_entry(path, config)
        judges = task_judges(path)
        if task["id"] in ids:
            raise ValueError(f"Duplicate task ID: {task['id']}")
        ids.add(task["id"])
        if task["name"] in names:
            raise ValueError(f"Duplicate task name: {task['name']}")
        names.add(task["name"])
        missing_env = [name for name in task_host_variables(path) if not os.environ.get(name)]
        if missing_env:
            print(f"{path}: deferred trials because {', '.join(missing_env)} is unset.", file=sys.stderr, flush=True)
        for key, agent in config.agents.items():
            if agents and key not in agents or models and agent.model not in models:
                continue
            model = config.models[agent.model]
            for mode in modes:
                if mode not in task["modes"] or mode not in agent.modes:
                    continue
                combinations += 1
                for number in [trial] if trial is not None else range(1, (n_attempts or config.n_attempts) + 1):
                    metadata = {"task_id": task["id"], "task_hash": task["hash"],
                                "skills_hash": skills_pack.hash if mode == "skills" else None,
                                "agent": None if mode == "vanilla" else agent.name, "model": model.name, "effort": model.effort,
                                "mode": mode, "trial": number}
                    identity = trial_identity(metadata)
                    if identity in selected:
                        raise ValueError("Selected agent settings produce duplicate trial identities")
                    selected.append(identity)
                    row = prior.get(identity, {})
                    retry = row.get("retry", -1)
                    if row.get("status") in {"passed", "failed"}:
                        continue
                    judge = {"model": config.judge.model, "effort": config.judge.effort} if judges else None
                    item = {**metadata, "task_path": str(path.resolve()), "agent_key": key,
                            "agent_version": agent.version, "harbor_version": config.harbor_version,
                            "paid_by": agent.paid_by,
                            "judge": judge, "judge_paid_by": config.judge.paid_by if judge else None}
                    recovery = retry_judge_error and row.get("judge") and row.get("error_kind") in {
                        "judge", "RewardFileNotFoundError", "RewardFileEmptyError", "VerifierOutputParseError"}
                    if row.get("error_kind") == "judge" and not recovery:
                        exhausted.append(row)
                        continue
                    policy = config.retry
                    exception = row.get("error_kind")
                    if row and not recovery and (retry >= policy.max_retries
                                or exception in (policy.exclude_exceptions or set())
                                or policy.include_exceptions and exception not in policy.include_exceptions):
                        exhausted.append(row)
                        continue
                    if missing_env:
                        deferred.append({**metadata, "task_path": str(path.resolve()), "agent_key": key,
                                         "missing_env": missing_env})
                        continue
                    reserve = agent.cost_limit_usd if agent.paid_by == "api_key" else 0.0
                    judge_calls = sum(judge.judge.samples * (len(judge.criterion) + 1
                                      if judge.judge.mode == "individual" else 1) for judge in judges.values())
                    # RewardKit 0.2.3 retries malformed replies up to three calls.
                    judge_reserve = config.judge.cost_limit_usd * judge_calls * 3 if config.judge.paid_by == "api_key" else 0.0
                    remaining = 1 if recovery else policy.max_retries - retry
                    missing.append({**item, "retry": retry + 1, "remaining_executions": remaining,
                                    "agent_reserve_usd": reserve, "judge_reserve_usd": judge_reserve,
                                    "worst_case_usd": (reserve + judge_reserve) * remaining})
    if not selected:
        raise ValueError("No tasks declare a selected mode and agent")
    if trial is not None and combinations != 1:
        raise ValueError("--trial requires exactly one task, agent, and mode")
    deferred_ids = {trial_identity(row) for row in deferred}
    return {"missing": missing, "missing_trials": len(missing), "exhausted_errors": exhausted, "deferred": deferred,
            "worst_case_usd": round(sum(row["worst_case_usd"] for row in missing), 8),
            "selected": [identity for identity in selected if identity not in deferred_ids]}


def budget_check(report: dict, budget: float | None, *, required=False) -> dict:
    if budget is not None and (not math.isfinite(budget) or budget < 0):
        raise ValueError("Budget must be a finite, nonnegative USD amount")
    if required and report["missing"] and budget is None:
        raise ValueError("A trial requires --budget before Harbor starts")
    report.update(budget_usd=budget, within_budget=budget is None or report["worst_case_usd"] <= budget)
    return report


@contextmanager
def readable_credentials(config: JobSettings, keys: set[str]):
    """Point Harbor at readable copies of the selected agents' credential files while trials run.

    Harbor copies a credential file into the task as root and keeps its mode, and task images run as
    `agent`, so a private file such as Codex's own `~/.codex/auth.json` is unreadable there and the
    agent runs logged out. The copies live in a private temporary directory and go when the run ends.
    Yields the copy for each host variable, since an agent env that fixes the variable outranks the
    host env in Harbor. A path declared without a host variable is left to Harbor as it is.
    """
    sources: dict[str, Path] = {}
    for key in sorted(keys):
        agent = config.agents[key]
        for credential in agent.required_files:
            variable, path = credential_file(agent, credential, key)
            if variable is None or not path.is_file():
                continue
            if sources.setdefault(variable, path) != path:
                raise ValueError(f"{variable} names different credential files")
    previous = {variable: os.environ.get(variable) for variable in sources}
    with tempfile.TemporaryDirectory(prefix="ethevals-credentials-") as directory:
        copies = {}
        try:
            for variable, path in sources.items():
                copy = Path(directory) / f"{variable}-{path.name}"
                shutil.copyfile(path, copy)
                copy.chmod(0o644)
                os.environ[variable] = copies[variable] = str(copy)
            yield copies
        finally:
            for variable, value in previous.items():
                if value is None:
                    os.environ.pop(variable, None)
                else:
                    os.environ[variable] = value


async def run(report: dict, config: JobSettings, output: Path, previous: list[dict], *,
              skills_pack: SkillsPack | None = None,
              publication_secrets: dict[str, set[bytes]] | None = None,
              agent_setup_timeout_multiplier: float | None = None) -> bool:
    if not report["within_budget"]:
        raise ValueError("Budget exceeded; no trials started")
    secrets = publication_secrets if publication_secrets is not None else secret_values(
        config, [Path(item["task_path"]) for item in report["missing"]])
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
        if task_entry(path, config)["hash"] != item["task_hash"]:
            raise ValueError("The task differs from the plan; plan the trials again")
        if item["judge"]:
            check_judge_key(config.judge)
    rows = previous
    with readable_credentials(config, {item["agent_key"] for item in report["missing"]}) as copies:
        prepared = []
        for item in report["missing"]:
            path = Path(item["task_path"])
            missing = [name for name in task_host_variables(path) if not os.environ.get(name)]
            if missing:
                raise ValueError(f"{path}: missing {', '.join(missing)}")
            agent = config.agents[item["agent_key"]]
            model = config.models[agent.model]
            check_credentials(agent, item["agent_key"])
            kwargs = {**model.kwargs, **agent.kwargs, "version": agent.version}
            env = {**agent.env, **{name: copies[name] for name in agent.env if name in copies}}
            # Harbor prefers a known name over import_path, so pass only one.
            harbor = AgentConfig(name=None if agent.import_path else agent.name, import_path=agent.import_path,
                                 model_name=model.name, kwargs=kwargs, env=env)
            options = AgentFactory.get_agent_class_from_config(harbor).options_model
            fields = options.model_fields if options is not None else {}
            if model.effort is not None:
                # OpenCode has no effort option; its model variant sets the provider's effort.
                effort = "variant" if "variant" in fields and "reasoning_effort" not in fields else "reasoning_effort"
                harbor.kwargs[effort] = model.effort
            if agent.paid_by == "api_key" and "max_budget_usd" in fields:
                harbor.kwargs["max_budget_usd"] = str(agent.cost_limit_usd)
            if item["mode"] == "skills":
                harbor.skills = [str(skills_path)]
            prepared.append((item, harbor))
        for item, harbor in prepared:
            try:
                name = hashlib.sha256(json.dumps([item, harbor.model_dump(mode="json")], sort_keys=True).encode()).hexdigest()[:24]
                destination = output / "jobs" / name
                destination.mkdir(parents=True, exist_ok=True)
                remember_secrets(destination, secrets)
                write_whole(destination / "board.json", json.dumps(item, indent=2) + "\n", output)
                config_path = destination / "config.json"
                if config_path.exists():
                    try:
                        JobConfig.model_validate_json(config_path.read_text())
                    except ValidationError:
                        if (any(child.is_dir() for child in destination.iterdir())
                                or (destination / "lock.json").exists() or (destination / "result.json").exists()):
                            raise ValueError(f"{config_path}: unreadable config beside started trials; preserve the saved job")
                        config_path.unlink()
                job = await Job.create(JobConfig(
                    job_name=name, jobs_dir=output / "jobs", n_concurrent_trials=1, quiet=True,
                    agents=[harbor], tasks=[{"path": item["task_path"]}],
                    verifier={"env": {
                        "REWARDKIT_JUDGE": config.judge.model,
                        "REWARDKIT_REASONING_EFFORT": config.judge.effort,
                        "CLAUDE_CODE_OAUTH_TOKEN": "", "REWARDKIT_FORCE_SUBSCRIPTION": "",
                    } if item["judge"] else {}}, environment={"type": "docker"},
                    agent_setup_timeout_multiplier=agent_setup_timeout_multiplier,
                ))
                await job.run()
            finally:
                check_output(output, secrets, require_inventory=True)
                rows = fold_rows(rows, recover_rows(output))
                write_rows(output / "rows.jsonl", rows)
    selected = {tuple(identity) for identity in report["selected"]}
    observed = {trial_identity(row): row for row in rows if trial_identity(row) in selected}
    return len(observed) == len(selected) and all(row["status"] != "error" for row in observed.values())
