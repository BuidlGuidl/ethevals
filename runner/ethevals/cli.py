import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="ethevals")
    commands = parser.add_subparsers(dest="command", required=True)
    parsers = {name: commands.add_parser(name) for name in
               ("run", "plan", "catalog", "export-hf", "publish-logs", "upload-hub")}
    for name in ("lint", "free-check"):
        parsers[name] = commands.add_parser(name, help="Check Harbor task folders.")
        parsers[name].add_argument("--tasks", nargs="+", type=Path, help="Task folders. Defaults to tasks/**/task.toml.")
        parsers[name].add_argument("--config", type=Path, help="Board-wide Harbor job settings.")
    parsers["free-check"].add_argument("--output", type=Path, default=Path("results/free-check"))
    for name in ("run", "plan", "catalog"):
        command = parsers[name]
        command.add_argument("--tasks", nargs="+", type=Path, help="Task folders. Defaults to tasks/**/task.toml.")
        command.add_argument("--config", type=Path, help="Board-wide Harbor job settings.")
    parsers["export-hf"].add_argument("--tasks", nargs="+", type=Path, help="Task folders. Defaults to tasks/**/task.toml.")
    parsers["run"].add_argument("--output", type=Path, default=Path("results"))
    parsers["plan"].add_argument("--output", type=Path, default=Path("results"))
    parsers["catalog"].add_argument("--output", type=Path, default=Path("results"))
    parsers["export-hf"].add_argument("--output", type=Path, required=True)
    parsers["publish-logs"].add_argument("--output", type=Path, required=True)
    parsers["upload-hub"].add_argument("--output", type=Path, required=True, help="Checked output directory to publish publicly to Harbor Hub.")
    parsers["upload-hub"].add_argument("--config", type=Path, help="Job settings with the Hub org and key variable.")
    parsers["run"].add_argument("--upload-hub", action="store_true", help="Publish checked job folders publicly to Harbor Hub.")
    for name in ("run", "plan"):
        command = parsers[name]
        command.description = "Job n_attempts sets scored repeats; retry.max_retries caps reruns after eligible errors."
        command.add_argument("--agents", nargs="+", help="Agent keys from the job config.")
        command.add_argument("--models", nargs="+", help="Model keys from the job config.")
        command.add_argument("--modes", nargs="+", help="Modes from the job config: vanilla, internet, or skills.")
        repeats = command.add_mutually_exclusive_group()
        repeats.add_argument("--n-attempts", type=positive, help="Number of scored trials per task, agent, and mode.")
        repeats.add_argument("--trial", type=positive, help="One numbered trial with one task, agent, and mode.")
        command.add_argument("--retry-judge-error", action="store_true",
                             help="With --trial, admit one fresh execution after a judge error under the budget.")
        command.add_argument("--rows", type=Path, default=Path("results/rows.jsonl"), help="Rows used to find missing trials.")
        command.add_argument("--budget", type=float, help="USD admission budget. Every agent trial requires an explicit budget.")
    parsers["export-hf"].add_argument("--hf-repo")
    parsers["export-hf"].add_argument("--license", help="HF dataset license identifier. Unset means undecided.")
    publisher = parsers["publish-logs"]
    publisher.add_argument("--repo", required=True, help="GitHub owner/repo for trajectories and verifier output.")
    publisher.add_argument("--run-id", required=True, help="Unique results run ID. The release tag is results-<run-id>.")
    publisher.add_argument("--commit", required=True, help="Full source commit SHA for the release tag.")
    publisher.add_argument("--publish", action="store_true", help="Create the GitHub release and upload trajectories and verifier output with gh.")
    return parser, parser.parse_args(argv)


def main(argv=None) -> int:
    parser, args = parse_args(argv)
    try:
        if args.command in {"plan", "run", "catalog"}:
            from . import jobs
            from .job_config import load_job
            from .trial_rows import previous_rows, write_rows

            paths = args.tasks or sorted(path.parent for path in Path("tasks").rglob("task.toml"))
            if args.command == "catalog":
                jobs.write_catalog(paths, args.output)
                return 0
            if not paths:
                raise ValueError("No task folders found. Use --tasks or start from the repository root.")
            config = load_job(args.config)
            skills_pack = jobs.pack_skills() if "skills" in (args.modes or config.modes) else None
            previous = previous_rows(args.output, args.rows)
            report = jobs.budget_check(jobs.plan(
                paths, config, previous, agents=args.agents, models=args.models, modes=args.modes,
                n_attempts=args.n_attempts, trial=args.trial, skills_pack=skills_pack,
                retry_judge_error=args.retry_judge_error,
            ), args.budget, required=args.command == "run")
            if args.command == "plan":
                print(json.dumps(report, indent=2))
                return 0 if report["within_budget"] else 1
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
            if not report["within_budget"]:
                raise ValueError("Budget exceeded; no trials started")
            write_rows(args.output / "rows.jsonl", previous)
            from .hub import upload_hub
            from .secret_check import secret_values
            from .trial_rows import recover_rows, fold_rows, read_rows

            secrets = secret_values(config, [Path(item["task_path"]) for item in report["missing"]])
            hub_key = os.environ.pop(config.hub.key_env, None) if config.hub else None
            try:
                success = asyncio.run(jobs.run(report, config, args.output, previous, skills_pack=skills_pack,
                                               publication_secrets=secrets))
            finally:
                if hub_key is not None:
                    os.environ[config.hub.key_env] = hub_key
            if args.upload_hub:
                upload_hub(args.output, config)
                write_rows(args.output / "rows.jsonl", fold_rows(read_rows(args.output / "rows.jsonl"), recover_rows(args.output)))
            print(f"Results rows: {args.output / 'rows.jsonl'}")
            return 0 if success else 1
        if args.command == "export-hf":
            from .hf import DEFAULT_REPO, write_hf

            paths = args.tasks or sorted(path.parent for path in Path("tasks").rglob("task.toml"))
            print(json.dumps(write_hf(paths, args.output, args.hf_repo or DEFAULT_REPO, args.license), indent=2))
            return 0
        if args.command in {"lint", "free-check"}:
            from harbor.models.task.task import Task
            from .harbor_tasks import lint_task
            from .job_config import load_job
            config = load_job(args.config)
            paths = args.tasks or sorted(path.parent for path in Path("tasks").rglob("task.toml"))
            if not paths:
                raise ValueError("No task folders found. Use --tasks or start from the repository root.")
            names = set()
            for path in paths:
                lint_task(path, config)
                name = Task(path).name
                if name in names:
                    raise ValueError(f"Duplicate task name: {name}")
                names.add(name)
                print(f"{path}: lint passed")
            if args.command == "free-check":
                from .harbor_tasks import free_check
                asyncio.run(free_check(paths, args.output))
            return 0
        if args.command == "upload-hub":
            from .hub import upload_hub
            from .job_config import load_job
            from .trial_rows import recover_rows, write_rows

            upload_hub(args.output, load_job(args.config))
            write_rows(args.output / "rows.jsonl", recover_rows(args.output))
            return 0
        if args.command == "publish-logs":
            from .publish import publish_logs

            print(json.dumps(publish_logs(args.output, args.repo, args.run_id, args.commit,
                                         publish=args.publish), indent=2))
            return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ethevals: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
