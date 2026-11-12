"""Plan missing trials and run them through Harbor."""
import hashlib
import json
import math
import os
import sys
from pathlib import Path

from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.task.task import Task
from harbor.agents.factory import AgentFactory
from harbor.models.trial.config import AgentConfig
from harbor.publisher.packager import Packager
from pydantic import ValidationError

from .files import write_whole
from .job_config import JobSettings, check_credentials, check_judge_key, load_job
from .harbor_tasks import lint_task, task_host_variables, task_judges
from .skills import SkillsPack, pack_skills
from .task_hashes import task_hashes
from .secret_check import check_output, remember_secrets, secret_values
from .trial_rows import fold_rows, recover_rows, trial_identity, write_rows
from .regrade import prepare_regrades, regrade_options, run_regrades


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
    config = config or load_job()
    judge = config.judge.identity() if task_judges(path) else None
    return {"id": f"{pillar}/{path.name}", "hash": "sha256:" + digest, "pillar": pillar,
            **task_hashes(path, judge),
            "area": metadata.get("area"), "layer": metadata.get("layer"),
            "name": task.name, "description": task.config.task.description,
            "instruction": (path / "instruction.md").read_text(), "modes": modes}


def write_catalog(paths: list[Path], output: Path) -> None:
    entries = [task_entry(path) for path in paths]
    for entry in entries:
        del entry["checks_inputs"]
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


def decide_saved_row(row: dict, current: dict, policy, *, retry_judge_error=False) -> dict:
    if row and any(row.get(key) != current[key] for key in ("instruction_hash", "environment_hash")):
        return {"action": "rerun", "reason": "The instruction or environment changed."}
    if row.get("status") in {"passed", "failed"}:
        if row.get("checks_hash") == current["checks_hash"]:
            return {"action": "keep"}
        before, after = row.get("checks_inputs", {}), current["checks_inputs"]
        changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
        if "@artifacts" in changed:
            return {"action": "rerun", "reason": "The saved work lacks the changed artifacts."}
        options = current["regrade"]
        judges = set(options["judge_files"])
        if row.get("checks_hash") in options.get("regrade_from", []):
            return {"action": "regrade", "kind": "evidence", "judge_required": bool(judges)}
        if judges and changed <= judges | {"@judge"}:
            if options.get("live_judge"):
                if options["kind"] == "workspace":
                    return {"action": "regrade", "kind": "workspace", "judge_required": True}
                return {"action": "rerun", "reason": "The judge needs a live browser or chain."}
            return {"action": "regrade", "kind": "judge", "judge_required": True}
        if options["kind"]:
            producer_changed = changed - judges - {"@judge", "tests/answer.py", "tests/hand-cases.json", "tests/reward.toml"}
            return {"action": "regrade", "kind": options["kind"],
                    "judge_required": bool(judges and (options["kind"] == "workspace" or changed & (judges | {"@judge"}) or producer_changed))}
        return {"action": "rerun", "reason": "The changed checks cannot use a saved-input regrade."}
    exception = row.get("error_kind")
    recovery = bool(retry_judge_error and row.get("judge") and exception in {
        "judge", "RewardFileNotFoundError", "RewardFileEmptyError", "VerifierOutputParseError"})
    if row and not recovery and (exception == "judge" or row.get("retry", -1) >= policy.max_retries
                or exception in (policy.exclude_exceptions or set())
                or policy.include_exceptions and exception not in policy.include_exceptions):
        return {"action": "exhausted"}
    return {"action": "retry", "recovery": recovery}


def plan(paths: list[Path], config: JobSettings, previous: list[dict], *, agents=None,
         models=None, modes=None, n_attempts=None, trial=None,
         skills_pack: SkillsPack | None = None, retry_judge_error=False, saved_work: Path | None = None,
         regrades_only=False) -> dict:
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
    missing, exhausted, selected, deferred, candidates = [], [], [], [], []
    ids, names = set(), set()
    combinations = 0
    for path in paths:
        task = task_entry(path, config)
        task["regrade"] = regrade_options(path)
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
                                **{key: task[key] for key in ("instruction_hash", "environment_hash", "checks_hash", "checks_inputs")},
                                "skills_hash": skills_pack.hash if mode == "skills" else None,
                                "agent": None if mode == "vanilla" else agent.name, "model": model.name, "effort": model.effort,
                                "mode": mode, "trial": number}
                    identity = trial_identity(metadata)
                    if identity in selected:
                        raise ValueError("Selected agent settings produce duplicate trial identities")
                    selected.append(identity)
                    row = prior.get(identity, {})
                    retry = row.get("retry", -1)
                    checks_changed = bool(row and row.get("checks_hash") != task["checks_hash"])
                    decision = decide_saved_row(row, task, config.retry, retry_judge_error=retry_judge_error)
                    if decision["action"] == "keep":
                        continue
                    if decision["action"] == "exhausted":
                        exhausted.append(row)
                        continue
                    judge = config.judge.identity() if judges else None
                    item = {**metadata, "task_path": str(path.resolve()), "agent_key": key,
                            "agent_version": agent.version, "harbor_version": config.harbor_version,
                            "paid_by": agent.paid_by,
                            "judge": judge, "judge_paid_by": config.judge.paid_by if judge else None}
                    item["checks_generation"] = row.get("checks_generation", 0) + int(checks_changed)
                    judge_calls = sum(j.judge.samples * (len(j.criterion) + 1
                                      if j.judge.mode == "individual" else 1) for j in judges.values())
                    judge_reserve = config.judge.cost_limit_usd * judge_calls * 3 if config.judge.paid_by == "api_key" else 0.0
                    reserve = agent.cost_limit_usd if agent.paid_by == "api_key" else 0.0
                    if decision["action"] in {"regrade", "rerun"}:
                        rerun = {**item, "retry": 0, "remaining_executions": config.retry.max_retries + 1,
                                 "agent_reserve_usd": reserve, "judge_reserve_usd": judge_reserve,
                                 "worst_case_usd": (reserve + judge_reserve) * (config.retry.max_retries + 1)}
                        if decision["action"] == "regrade":
                            if decision["kind"] == "workspace" and missing_env:
                                deferred.append({**item, "missing_env": missing_env})
                                continue
                            candidates.append({**item, "kind": decision["kind"], "judge_required": decision["judge_required"],
                                               "source_row": row, "retry": row["retry"], "rerun": rerun,
                                               "worst_case_usd": judge_reserve if decision["judge_required"] else 0.0})
                        elif missing_env:
                            deferred.append({**item, "missing_env": missing_env})
                        else:
                            missing.append({**rerun, "rerun_reason": decision["reason"]})
                        continue
                    recovery = decision["recovery"]
                    if missing_env:
                        deferred.append({**item, "missing_env": missing_env})
                        continue
                    remaining = 1 if recovery else config.retry.max_retries - retry
                    missing.append({**item, "retry": retry + 1, "remaining_executions": remaining,
                                    "agent_reserve_usd": reserve, "judge_reserve_usd": judge_reserve,
                                    "worst_case_usd": (reserve + judge_reserve) * remaining})
    if not selected:
        raise ValueError("No tasks declare a selected mode and agent")
    if trial is not None and combinations != 1:
        raise ValueError("--trial requires exactly one task, agent, and mode")
    deferred_ids = {trial_identity(row) for row in deferred}
    regrades, unavailable, pending = prepare_regrades(candidates, saved_work or Path("results/saved-work"))
    deferred.extend(pending)
    deferred_ids.update(trial_identity(item) for item in pending)
    for item in unavailable:
        path = Path(item["task_path"])
        absent = [name for name in task_host_variables(path) if not os.environ.get(name)]
        if absent:
            deferred.append({**item["rerun"], "missing_env": absent, "rerun_reason": item["rerun_reason"]})
            deferred_ids.add(trial_identity(item))
        else:
            missing.append({**item["rerun"], "rerun_reason": item["rerun_reason"]})
    if regrades_only:
        missing, selected = [], [trial_identity(item) for item in regrades]
    return {"missing": missing, "missing_trials": len(missing), "exhausted_errors": exhausted, "deferred": deferred,
            "regrades": regrades, "regrade_trials": len(regrades),
            "worst_case_usd": round(sum(row["worst_case_usd"] for row in [*missing, *regrades]), 8),
            "selected": [identity for identity in selected if identity not in deferred_ids]}


def budget_check(report: dict, budget: float | None, *, required=False) -> dict:
    if budget is not None and (not math.isfinite(budget) or budget < 0):
        raise ValueError("Budget must be a finite, nonnegative USD amount")
    if required and (report["missing"] or report.get("regrades")) and budget is None:
        raise ValueError("A trial requires --budget before Harbor starts")
    report.update(budget_usd=budget, within_budget=budget is None or report["worst_case_usd"] <= budget)
    return report


async def run(report: dict, config: JobSettings, output: Path, previous: list[dict], *,
              skills_pack: SkillsPack | None = None,
              publication_secrets: dict[str, set[bytes]] | None = None) -> bool:
    if not report["within_budget"]:
        raise ValueError("Budget exceeded; no trials started")
    secrets = publication_secrets if publication_secrets is not None else secret_values(
        config, [Path(item["task_path"]) for item in [*report["missing"], *report.get("regrades", [])]])
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
    for item in [*report["missing"], *report.get("regrades", [])]:
        path = Path(item["task_path"])
        current = task_entry(path, config)
        if (current["hash"] != item["task_hash"] or any(current[key] != item[key]
                for key in ("instruction_hash", "environment_hash", "checks_hash"))):
            raise ValueError("The task differs from the plan; plan the trials again")
        if item["judge"] and item.get("judge_required", True):
            check_judge_key(config.judge)
        if item.get("kind") == "workspace":
            missing = [name for name in task_host_variables(path) if not os.environ.get(name)]
            if missing:
                raise ValueError(f"{path}: missing {', '.join(missing)}")
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
        # Harbor prefers a known name over import_path, so pass only one.
        harbor = AgentConfig(name=None if agent.import_path else agent.name, import_path=agent.import_path,
                             model_name=model.name, kwargs=kwargs, env=agent.env)
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
    regrades = report.get("regrades", [])
    rows = run_regrades([item for item in regrades if item["kind"] != "workspace"], config, output, previous, secrets)
    for item in regrades:
        if item["kind"] == "workspace":
            harbor = AgentConfig(import_path="ethevals.saved_agent:SavedWorkAgent", kwargs={"trial": item["saved_work"]["trial"]})
            rows = await run_trial(item, harbor, config, output, secrets, rows)
    for item, harbor in prepared:
        for no_answer_try in range(2):
            rows = await run_trial(item, harbor, config, output, secrets, rows)
            row = next((row for row in recover_rows(output) if trial_identity(row) == trial_identity(item)
                        and row["retry"] == item["retry"]
                        and row.get("checks_generation", 0) == item["checks_generation"]), None)
            if no_answer_try or row is None or row.get("error_kind") != "no_answer":
                break
            item = {**item, "no_answer": row["no_answer"]}
    selected = {tuple(identity) for identity in report["selected"]}
    observed = {trial_identity(row): row for row in rows if trial_identity(row) in selected}
    return (len(observed) == len(selected) and all(row["status"] != "error" for row in observed.values())
            and all(observed[trial_identity(item)]["checks_hash"] == item["checks_hash"] for item in report.get("regrades", [])))


async def run_trial(item, harbor, config, output, secrets, rows):
    try:
        name = hashlib.sha256(json.dumps([item, harbor.model_dump(mode="json")], sort_keys=True).encode()).hexdigest()[:24]
        destination = output / "jobs" / name
        destination.mkdir(parents=True, exist_ok=True)
        remember_secrets(destination, secrets)
        write_whole(destination / "board.json", json.dumps(item, indent=2) + "\n", output)
        if item.get("kind") == "workspace":
            write_whole(destination / "regrade.json", json.dumps([item], indent=2) + "\n", output)
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
            verifier={"env": config.judge.environment() if item["judge"] else {}}, environment={"type": "docker"},
        ))
        await job.run()
    finally:
        check_output(output, secrets, require_inventory=True)
        rows = fold_rows(rows, recover_rows(output))
        write_rows(output / "rows.jsonl", rows)
    return rows
