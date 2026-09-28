import argparse
import json
import math
import os
import subprocess
from pathlib import Path

from .catalog import write_catalog
from .config import load_config
from .loader import load_eval
from .runner import run
from .actors import select_actors
from .hf import DEFAULT_REPO, write_hf
from .publish import publish_logs
from .planning import plan
from .rows import read_rows


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(prog="ethevals")
    commands = parser.add_subparsers(dest="command", required=True)
    parsers = {name: commands.add_parser(name) for name in
               ("run", "plan", "check", "validate", "catalog", "export-hf", "prove-hf", "publish-logs")}
    for name, command in parsers.items():
        command.add_argument("--evals", nargs="+", help="Eval folders. Defaults to evals/*/*.")
        command.add_argument("--config", type=Path)
        if name != "validate":
            command.add_argument("--output", type=Path, required=name in {"export-hf", "prove-hf", "publish-logs"},
                                 default=Path("results") if name in {"run", "plan", "check", "catalog"} else None)
    for name in ("run", "plan", "check"):
        command = parsers[name]
        command.add_argument("--modes", nargs="+", help="Select vanilla, internet, or skills.")
        command.add_argument("--epochs", type=positive)
        command.add_argument("--mock-delay", type=float, default=0, help="Pause each mock epoch, for resume checks.")
        command.add_argument("--retry-errors", action="store_true", help="Grant one further attempt to each selected error epoch.")
    for name in ("run", "plan"):
        parsers[name].add_argument("--models", nargs="+", help="Model names from config.yaml.")
        parsers[name].add_argument("--answer", choices=["reference", "empty", "default"], help="Use mockllm without an API call.")
        parsers[name].add_argument("--rows", type=Path, help="Committed rows used to find missing epochs.")
    parsers["plan"].add_argument("--budget", type=float, help="Exit 1 if the worst case exceeds this USD budget.")
    parsers["check"].set_defaults(models=None, answer=None)
    parsers["export-hf"].add_argument("--hf-repo", default=os.environ.get("ETHEVALS_HF_REPO", DEFAULT_REPO))
    parsers["export-hf"].add_argument("--license", default=os.environ.get("ETHEVALS_DATASET_LICENSE"), help="HF dataset license identifier. Unset means undecided.")
    parsers["prove-hf"].add_argument("--export", type=Path, required=True)
    publisher = parsers["publish-logs"]
    publisher.add_argument("--repo", required=True, help="GitHub owner/repo for log assets.")
    publisher.add_argument("--run-id", required=True, help="Unique results run ID. The release tag is results-<run-id>.")
    publisher.add_argument("--commit", required=True, help="Full source commit SHA for the release tag.")
    publishing = publisher.add_mutually_exclusive_group()
    publishing.add_argument("--dry-run", action="store_true", help="Print the publish plan without writes or network calls. This is the default.")
    publishing.add_argument("--publish", action="store_true", help="Create the GitHub release and upload referenced logs with gh.")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        paths = [Path(value) for value in args.evals] if args.evals else sorted(Path("evals").glob("*/*"))
        if not paths:
            raise ValueError("No eval folders found. Use --evals or start from the repository root.")
        evals = [load_eval(path, config) for path in paths]
        if args.command == "publish-logs":
            print(json.dumps(publish_logs(args.output, args.repo, args.run_id, args.commit,
                                         current_hashes={item.id: item.hash for item in evals},
                                         publish=args.publish), indent=2))
            return 0
        if args.command == "prove-hf":
            from .hf_proof import prove
            print(json.dumps(prove(args.export, evals, args.output, config), indent=2))
            return 0
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
        if args.models and args.answer:
            raise ValueError("--models cannot be combined with key-free checks")
        unknown = set(args.models or []) - config.models.keys()
        if unknown:
            raise ValueError(f"Unknown model names: {', '.join(sorted(unknown))}")
        if args.mock_delay < 0 or (args.mock_delay and not (args.answer or args.command == "check")):
            raise ValueError("--mock-delay requires a key-free check and a nonnegative value")
        if args.command == "plan":
            if args.budget is not None and (not math.isfinite(args.budget) or args.budget < 0):
                raise ValueError("--budget must be a finite, nonnegative USD amount")
            players, _ = select_actors(config, args.models, args.modes, args.answer, planning=True)
            report = plan(evals, config, players, read_rows(args.rows or args.output / "rows.jsonl"),
                          epochs=args.epochs, retry_errors=args.retry_errors)
            report["budget_usd"] = args.budget
            report["within_budget"] = args.budget is None or report["worst_case_usd"] <= args.budget
            print(json.dumps(report, indent=2))
            return 0 if report["within_budget"] else 1
        if args.command == "run" and not args.answer and not os.environ.get("OPENROUTER_API_KEY"):
            raise ValueError("OPENROUTER_API_KEY is required. Use --answer reference for a key-free epoch.")
        answers = ["reference", "empty"] if args.command == "check" else [args.answer]
        passed = True
        for answer in answers:
            output = args.output / answer if args.command == "check" else args.output
            players, grade = select_actors(config, args.models, args.modes, answer, args.mock_delay)
            success, rows = run(evals, config, output, players=players, grade=grade,
                                epochs=args.epochs, fresh=args.command == "check", retry_errors=args.retry_errors,
                                rows_file=args.rows if args.command == "run" else None)
            if args.command == "check":
                success = success and bool(rows) and all(row["passed"] is (answer == "reference") for row in rows)
            passed = passed and success
            print(f"{len(rows)} results rows: {output / 'rows.jsonl'}")
        return 0 if passed else 1
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ethevals: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
