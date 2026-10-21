import argparse
import asyncio
import json
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
               ("run", "plan", "check", "validate", "catalog", "export-hf", "publish-logs")}
    for name in ("lint", "free-check"):
        parsers[name] = commands.add_parser(name, help="Check Harbor task folders.")
        parsers[name].add_argument("--tasks", nargs="+", type=Path, help="Task folders. Defaults to tasks/**/task.toml.")
    parsers["free-check"].add_argument("--output", type=Path, default=Path("results/free-check"))
    for name in ("run", "plan", "catalog"):
        command = parsers[name]
        command.add_argument("--tasks", nargs="+", type=Path, help="Task folders. Defaults to tasks/**/task.toml.")
        command.add_argument("--config", type=Path, help="Board-wide Harbor job settings.")
    for name in ("check", "validate", "export-hf"):
        parsers[name].add_argument("--evals", nargs="+", help="Eval folders. Defaults to evals/*/*.")
        parsers[name].add_argument("--config", type=Path)
        parsers[name].set_defaults(effort=None)
    parsers["run"].add_argument("--output", type=Path, default=Path("results"))
    parsers["plan"].add_argument("--output", type=Path, default=Path("results"))
    parsers["check"].add_argument("--output", type=Path, default=Path("results/check"))
    parsers["catalog"].add_argument("--output", type=Path, default=Path("results"))
    parsers["export-hf"].add_argument("--output", type=Path, required=True)
    parsers["publish-logs"].add_argument("--output", type=Path, required=True)
    for name in ("check",):
        command = parsers[name]
        command.add_argument("--modes", nargs="+", help="Select vanilla, internet, or skills.")
        repeats = command.add_mutually_exclusive_group()
        repeats.add_argument("--epochs", type=positive)
        command.add_argument("--retry-errors", action="store_true", help="Grant one further attempt to each selected error epoch.")
    for name in ("run", "plan"):
        command = parsers[name]
        command.add_argument("--agents", nargs="+", help="Agent keys from the job config.")
        command.add_argument("--models", nargs="+", help="Model keys from the job config.")
        command.add_argument("--modes", nargs="+", help="Modes from the job config: vanilla, internet, or skills.")
        repeats = command.add_mutually_exclusive_group()
        repeats.add_argument("--trials", type=positive)
        repeats.add_argument("--trial", type=positive, help="One numbered trial with one task, agent, and mode.")
        command.add_argument("--retry-errors", action="store_true", help="Grant one further attempt to selected errors.")
        command.add_argument("--rows", type=Path, default=Path("results/rows.jsonl"), help="Rows used to find missing trials.")
        command.add_argument("--budget", type=float, help="USD admission budget. Every agent trial requires an explicit budget.")
    parsers["check"].set_defaults(agents=None, models=None)
    parsers["export-hf"].add_argument("--hf-repo")
    parsers["export-hf"].add_argument("--license", help="HF dataset license identifier. Unset means undecided.")
    publisher = parsers["publish-logs"]
    publisher.add_argument("--repo", required=True, help="GitHub owner/repo for log assets.")
    publisher.add_argument("--run-id", required=True, help="Unique results run ID. The release tag is results-<run-id>.")
    publisher.add_argument("--commit", required=True, help="Full source commit SHA for the release tag.")
    publisher.add_argument("--publish", action="store_true", help="Create the GitHub release and upload referenced logs with gh.")
    return parser, parser.parse_args(argv)


def main(argv=None) -> int:
    parser, args = parse_args(argv)
    try:
        if args.command in {"plan", "run", "catalog"}:
            from . import jobs
            from .trial_rows import previous_rows, write_rows

            paths = args.tasks or sorted(path.parent for path in Path("tasks").rglob("task.toml"))
            if args.command == "catalog":
                jobs.write_catalog(paths, args.output)
                return 0
            if not paths:
                raise ValueError("No task folders found. Use --tasks or start from the repository root.")
            config = jobs.load_job(args.config)
            skills_pack = jobs.pack_skills() if "skills" in (args.modes or config.modes) else None
            previous = previous_rows(args.output, args.rows)
            report = jobs.budget_check(jobs.plan(
                paths, config, previous, agents=args.agents, models=args.models, modes=args.modes,
                trials=args.trials, trial=args.trial, retry_errors=args.retry_errors, skills_pack=skills_pack,
            ), args.budget, required=args.command == "run")
            if args.command == "plan":
                print(json.dumps(report, indent=2))
                return 0 if report["within_budget"] else 1
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
            if not report["within_budget"]:
                raise ValueError("Budget exceeded; no trials started")
            write_rows(args.output / "rows.jsonl", previous)
            success = asyncio.run(jobs.run(report, config, args.output, previous, skills_pack=skills_pack))
            print(f"Results rows: {args.output / 'rows.jsonl'}")
            return 0 if success else 1
        if args.command in {"lint", "free-check"}:
            from .harbor_tasks import lint_task
            paths = args.tasks or sorted(path.parent for path in Path("tasks").rglob("task.toml"))
            if not paths:
                raise ValueError("No task folders found. Use --tasks or start from the repository root.")
            for path in paths:
                lint_task(path)
                print(f"{path}: lint passed")
            if args.command == "free-check":
                from .harbor_tasks import free_check
                asyncio.run(free_check(paths, args.output))
            return 0
        if args.command == "publish-logs":
            from .publish import publish_logs

            print(json.dumps(publish_logs(args.output, args.repo, args.run_id, args.commit,
                                         publish=args.publish), indent=2))
            return 0
        from .config import load_config
        from .loader import load_eval
        from .runner import run
        from .checks import available_checks
        from .skills import pack_skills

        config = load_config(args.config, effort=args.effort)
        paths = [Path(value) for value in args.evals] if args.evals else sorted(Path("evals").glob("*/*"))
        if not paths and args.command != "catalog":
            raise ValueError("No eval folders found. Use --evals or start from the repository root.")
        skills_pack = pack_skills()
        evals = [load_eval(path, config, skills_pack) for path in paths]
        if args.command == "check":
            evals = available_checks(evals)
            if not evals:
                return 0
        if args.command == "export-hf":
            from .hf import DEFAULT_REPO, write_hf

            print(json.dumps(write_hf(evals, args.output, args.hf_repo or DEFAULT_REPO, args.license), indent=2))
            return 0
        if args.command == "validate":
            for evaluation in evals:
                print(f"{evaluation.id} {evaluation.hash}")
            return 0
        answers = ["reference", "empty"]
        passed = True
        for answer in answers:
            output = args.output / answer
            success, rows = run(evals, config, output, agents=args.agents, models=args.models, modes=args.modes, answer=answer,
                                epochs=args.epochs, fresh=args.command == "check", retry_errors=args.retry_errors,
                                epoch=None, rows_file=None, budget=None)
            if args.command == "check":
                success = success and bool(rows) and all(row["status"] == ("passed" if answer == "reference" else "failed") for row in rows)
            passed = passed and success
            print(f"{len(rows)} results rows: {output / 'rows.jsonl'}")
        return 0 if passed else 1
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ethevals: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
