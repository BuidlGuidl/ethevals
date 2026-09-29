import argparse
import json
import subprocess
from pathlib import Path

from .catalog import write_catalog
from .config import load_config
from .loader import load_eval
from .runner import run
from .actors import select_actors
from .hf import DEFAULT_REPO, write_hf
from .publish import publish_logs
from .planning import plan, budget_check
from .rows import previous_rows


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
    for name in ("run", "plan", "check", "validate", "catalog", "export-hf"):
        parsers[name].add_argument("--evals", nargs="+", help="Eval folders. Defaults to evals/*/*.")
        parsers[name].add_argument("--config", type=Path)
    parsers["run"].add_argument("--output", type=Path, default=Path("results"))
    parsers["plan"].add_argument("--output", type=Path, default=Path("results"))
    parsers["check"].add_argument("--output", type=Path, default=Path("results/check"))
    parsers["catalog"].add_argument("--output", type=Path, default=Path("results"))
    parsers["export-hf"].add_argument("--output", type=Path, required=True)
    parsers["publish-logs"].add_argument("--output", type=Path, required=True)
    for name in ("run", "plan", "check"):
        command = parsers[name]
        command.add_argument("--modes", nargs="+", help="Select vanilla, internet, or skills.")
        command.add_argument("--epochs", type=positive)
        command.add_argument("--retry-errors", action="store_true", help="Grant one further attempt to each selected error epoch.")
    for name in ("run", "plan"):
        parsers[name].add_argument("--agents", nargs="+", help="Agent names from config.yaml.")
        parsers[name].add_argument("--rows", type=Path, default=Path("results/rows.jsonl"), help="Committed rows used to find missing epochs.")
        parsers[name].add_argument("--budget", type=float, help="USD ceiling. Required for missing paid epochs.")
        parsers[name].add_argument("--wall-seconds", type=float, help="Bound preparation and scheduled epochs in wall seconds.")
    parsers["check"].set_defaults(agents=None)
    parsers["export-hf"].add_argument("--hf-repo", default=DEFAULT_REPO)
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
        if args.command == "publish-logs":
            print(json.dumps(publish_logs(args.output, args.repo, args.run_id, args.commit,
                                         publish=args.publish), indent=2))
            return 0
        config = load_config(args.config)
        paths = [Path(value) for value in args.evals] if args.evals else sorted(Path("evals").glob("*/*"))
        if not paths:
            raise ValueError("No eval folders found. Use --evals or start from the repository root.")
        evals = [load_eval(path, config) for path in paths]
        if args.command == "export-hf":
            print(json.dumps(write_hf(evals, args.output, args.hf_repo, args.license), indent=2))
            return 0
        if args.command == "catalog":
            write_catalog(evals, args.output)
            return 0
        if args.command == "validate":
            for evaluation in evals:
                print(f"{evaluation.id} {evaluation.hash}")
            return 0
        if args.command == "plan":
            agents_for, _ = select_actors(config, args.agents, args.modes, planning=True)
            report = budget_check(plan(evals, config, agents_for, previous_rows(args.output, args.rows),
                          epochs=args.epochs, retry_errors=args.retry_errors, wall_seconds=args.wall_seconds).report, args.budget)
            print(json.dumps(report, indent=2))
            return 0 if report["within_budget"] else 1
        answers = ["reference", "empty"] if args.command == "check" else [None]
        passed = True
        for answer in answers:
            output = args.output / answer if args.command == "check" else args.output
            success, rows = run(evals, config, output, agents=args.agents, modes=args.modes, answer=answer,
                                epochs=args.epochs, fresh=args.command == "check", retry_errors=args.retry_errors,
                                rows_file=args.rows if args.command == "run" else None,
                                budget=args.budget if args.command == "run" else None,
                                wall_seconds=args.wall_seconds if args.command == "run" else None)
            if args.command == "check":
                success = success and bool(rows) and all(row["status"] == ("passed" if answer == "reference" else "failed") for row in rows)
            passed = passed and success
            print(f"{len(rows)} results rows: {output / 'rows.jsonl'}")
        return 0 if passed else 1
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ethevals: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
