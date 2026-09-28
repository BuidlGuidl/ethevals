import argparse
import os
from pathlib import Path

from .catalog import write_catalog
from .config import load_config
from .loader import load_eval
from .runner import run


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(prog="ethevals")
    parser.add_argument("command", choices=["run", "check", "validate", "catalog"])
    parser.add_argument("--evals", nargs="+", help="Eval folders. Defaults to evals/*/*.")
    parser.add_argument("--models", nargs="+", help="Model names from config.yaml. Defaults to all configured models.")
    parser.add_argument("--modes", nargs="+", help="Select vanilla, internet, or skills. Run defaults to vanilla; check selects by type.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--epochs", type=positive)
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--answer", choices=["reference", "empty", "default"], help="Use mockllm without an API call.")
    parser.add_argument("--mock-delay", type=float, default=0, help="Pause each mock epoch, for resume checks.")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        paths = [Path(value) for value in args.evals] if args.evals else sorted(Path("evals").glob("*/*"))
        if not paths:
            raise ValueError("No eval folders found. Use --evals or start from the repository root.")
        evals = [load_eval(path, config) for path in paths]
        if args.command == "catalog":
            write_catalog(evals, args.output)
            return 0
        if args.command == "validate":
            for evaluation in evals:
                print(f"{evaluation.id} {evaluation.hash}")
            return 0
        if args.models and (args.answer or args.command == "check"):
            raise ValueError("--models cannot be combined with key-free checks")
        unknown = set(args.models or []) - config.models.keys()
        if unknown:
            raise ValueError(f"Unknown model names: {', '.join(sorted(unknown))}")
        if args.mock_delay < 0 or (args.mock_delay and not (args.answer or args.command == "check")):
            raise ValueError("--mock-delay requires a key-free check and a nonnegative value")
        if args.command == "run" and not args.answer and not os.environ.get("OPENROUTER_API_KEY"):
            raise ValueError("OPENROUTER_API_KEY is required. Use --answer reference for a key-free epoch.")
        if args.command == "check" and args.answer:
            raise ValueError("check chooses both reference and empty answers; omit --answer")
        answers = ["reference", "empty"] if args.command == "check" else [args.answer]
        passed = True
        for answer in answers:
            output = args.output / answer if args.command == "check" else args.output
            success, rows = run(evals, config, output, models=args.models, modes=args.modes,
                                answer=answer, epochs=args.epochs, delay=args.mock_delay, fresh=args.command == "check")
            if args.command == "check":
                success = success and bool(rows) and all(row["passed"] is (answer == "reference") for row in rows)
            passed = passed and success
            print(f"{len(rows)} results rows: {output / 'rows.jsonl'}")
        return 0 if passed else 1
    except (ValueError, OSError) as error:
        parser.exit(2, f"ethevals: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
