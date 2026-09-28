"""Local entry points for the workflows. Remote writes require --publish."""
import argparse
import base64
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from ethevals.actors import select_actors
from ethevals.config import load_config
from ethevals.hf import write_hf
from ethevals.hf_proof import prove
from ethevals.loader import load_eval
from ethevals.planning import plan
from ethevals.publish import publish_logs
from ethevals.rows import fold_rows, read_rows, write_rows
from ethevals.runner import run
from ethevals.sandboxes import IMAGES, validate_compose

RESULTS_BRANCH = "ci/results"


def command(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, text=True, **kwargs)


def restore_results(rows):
    """Read rows from the pending results PR without executing that branch's code."""
    ref = f"refs/remotes/origin/{RESULTS_BRANCH}"
    if subprocess.run(["git", "show-ref", "--verify", "--quiet", ref]).returncode == 0:
        content = command("git", "show", f"{ref}:results/rows.jsonl", capture_output=True).stdout
        pending = [json.loads(line) for line in content.splitlines() if line.strip()]
        write_rows(rows, fold_rows(read_rows(rows), pending))


def after_merge(args, evals, config):
    if not math.isfinite(args.budget) or args.budget < 0:
        raise ValueError("Budget must be a finite, nonnegative USD amount")
    if args.output.exists():
        raise ValueError("Use a fresh output directory for each CI run")
    if args.restore_results:
        restore_results(args.rows)
    previous = read_rows(args.rows)
    players, _ = select_actors(config, args.models, args.modes, args.answer, planning=True)
    report = plan(evals, config, players, previous, epochs=args.epochs)
    report.update(budget_usd=args.budget, within_budget=report["worst_case_usd"] <= args.budget)
    args.output.mkdir(parents=True)
    (args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    if not report["within_budget"]:
        print("Budget exceeded. No player or grader ran. Set a higher budget and dispatch again.", file=sys.stderr)
        return 1
    if not report["missing"]:
        write_rows(args.output / "rows.jsonl", previous)
        return 0
    if not args.answer and not os.environ.get("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is required for missing paid epochs")
    players, grade = select_actors(config, args.models, args.modes, args.answer)
    success, _ = run(evals, config, args.output, players=players, grade=grade,
                     rows_file=args.rows, epochs=args.epochs)
    # Publication runs even after execution errors, so their attempts survive checkout.
    (args.output / "execution.json").write_text(json.dumps({"success": success}) + "\n")
    if args.answer:
        write_rows(args.rows, fold_rows(previous, read_rows(args.output / "rows.jsonl")))
    print(f"{len(read_rows(args.output / 'rows.jsonl'))} rows after the run; execution success: {success}")
    return 0


def results_pr(rows, repo, publish):
    if not publish:
        print(f"Dry run: commit {rows} to {RESULTS_BRANCH} and open a results PR against main.")
        return
    command("git", "add", "--", rows)
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode
    if changed == 0:
        print("No row changes; no results PR needed.")
        return
    environment = {**os.environ, "GIT_AUTHOR_NAME": "github-actions[bot]", "GIT_COMMITTER_NAME": "github-actions[bot]",
                   "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                   "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
    tree = command("git", "write-tree", capture_output=True).stdout.strip()
    parents = ["-p", "HEAD"]
    ref = f"refs/remotes/origin/{RESULTS_BRANCH}"
    if subprocess.run(["git", "show-ref", "--verify", "--quiet", ref]).returncode == 0:
        parents += ["-p", ref]
    # Two parents retain main's source and append to the pending PR without a force push.
    commit = command("git", "commit-tree", tree, *parents, "-m", "Record eval results and log links",
                     capture_output=True, env=environment).stdout.strip()
    auth = base64.b64encode(f"x-access-token:{os.environ['GH_TOKEN']}".encode()).decode()
    command("git", "push", "origin", f"{commit}:refs/heads/{RESULTS_BRANCH}",
            env={**environment, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                 "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}"})
    existing = json.loads(command("gh", "pr", "list", "--repo", repo, "--head", RESULTS_BRANCH,
                                  "--base", "main", "--state", "open", "--json", "number", capture_output=True).stdout)
    if not existing:
        command("gh", "pr", "create", "--repo", repo, "--head", RESULTS_BRANCH, "--base", "main",
                "--title", "Record eval results", "--body",
                "Add completed epochs and execution errors. Full logs for scored epochs link to results releases. "
                "Approve the PR checks before merging. Inspect errors before granting further attempts.")


def publish_results(args, evals):
    report = publish_logs(args.output, args.repo, args.run_id, args.commit,
                          current_hashes={item.id: item.hash for item in evals}, publish=args.publish)
    print(json.dumps(report, indent=2))
    if args.publish:
        write_rows(args.rows, fold_rows(read_rows(args.rows), read_rows(args.output / "rows.jsonl"),
                                       read_rows(Path(report["rows_file"]))))
    if args.open_pr:
        if report["assets"] and not args.publish:
            print("Dry run: publication must succeed before folding linked rows and opening the PR.")
        else:
            results_pr(args.rows, args.repo, args.publish)
    execution = args.output / "execution.json"
    if execution.exists() and not json.loads(execution.read_text())["success"]:
        print("Results retained. Some evals have execution or discovery errors.", file=sys.stderr)
        return 1
    return 0


def checks(args, evals):
    for path in IMAGES.glob("*.compose.yaml"):
        validate_compose(path, stock=True)
    command(sys.executable, "-m", "ethevals.cli", "validate")
    command(sys.executable, "-m", "ethevals.cli", "check", "--output", args.output / "check")
    command(sys.executable, "-m", "pytest", "-q")
    command(sys.executable, "-m", "pytest", "-q", "--run-docker", "-m", "docker",
            "--ignore=inspect-runner/tests/test_agent_docker.py")
    write_hf(evals, args.output / "hf", "ethereum-foundation/hf-ethevals-dataset", None)
    prove(args.output / "hf", evals, args.output / "hf-proof", load_config())
    for task in ("test", "typecheck", "lint", "build"):
        command("pnpm", task, cwd="site")
    return 0


def release(args, evals):
    if not args.license:
        raise ValueError("Choose the dataset license before a release")
    report = write_hf(evals, args.output, args.hf_repo, args.license)
    print(json.dumps(report, indent=2))
    command_line = ["hf", "upload", args.hf_repo, str(args.output), ".", "--repo-type", "dataset"]
    if args.publish:
        command(*command_line)
    else:
        print(json.dumps({"dry_run": True, "command": command_line}))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["checks", "after-merge", "publish-results", "release"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=Path, default=Path("results/rows.jsonl"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--evals", nargs="+")
    parser.add_argument("--models", nargs="+")
    parser.add_argument("--modes", nargs="+", default=["vanilla", "internet"])
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--answer", choices=["reference", "empty", "default"])
    parser.add_argument("--budget", type=float, default=0)
    parser.add_argument("--restore-results", action="store_true")
    parser.add_argument("--repo")
    parser.add_argument("--run-id")
    parser.add_argument("--commit")
    parser.add_argument("--open-pr", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--hf-repo", default="ethereum-foundation/hf-ethevals-dataset")
    parser.add_argument("--license")
    args = parser.parse_args()
    if args.epochs is not None and args.epochs < 1:
        parser.error("--epochs must be at least 1")
    if args.models and args.answer:
        parser.error("--models cannot be combined with --answer")
    if args.command == "publish-results" and not all((args.repo, args.run_id, args.commit)):
        parser.error("publish-results requires --repo, --run-id, and --commit")
    try:
        config = load_config(args.config)
        if set(args.models or []) - config.models.keys():
            raise ValueError("Unknown model selection")
        evals = [load_eval(Path(path), config) for path in args.evals or sorted(Path("evals").glob("*/*"))]
        if args.command == "after-merge":
            return after_merge(args, evals, config)
        return {"checks": checks, "publish-results": publish_results, "release": release}[args.command](args, evals)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ci: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
