"""Local entry points for the workflows. Remote writes require --publish."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from inspect_ai.log import read_eval_log

from ethevals.cli import positive
from ethevals.config import load_config
from ethevals.hf import DEFAULT_REPO, write_hf
from ethevals.loader import load_eval
from ethevals.publish import publish_logs
from ethevals.rows import fold_rows, read_rows, write_rows, store_rows
from ethevals.runner import run
from ethevals.sandboxes import IMAGES, validate_compose

RESULTS_BRANCH = "ci/results"


def command(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, text=kwargs.pop("text", True), **kwargs)


def stored_file(ref, path):
    result = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    if result.returncode:
        return None
    return result.stdout


def result_record(own_rows=()):
    rows = []
    for ref in ("refs/remotes/origin/main", f"refs/remotes/origin/{RESULTS_BRANCH}"):
        content = stored_file(ref, "results/rows.jsonl") or ""
        rows = fold_rows(rows, [json.loads(line) for line in content.splitlines() if line.strip()])
    return fold_rows(rows, own_rows)


def restore_results(rows):
    """Read rows from the pending results PR without executing that branch's code."""
    write_rows(rows, result_record())


def after_merge(args, evals, config):
    if args.output.exists():
        raise ValueError("Use a fresh output directory for each CI run")
    args.output.mkdir(parents=True)
    if args.restore_results:
        restore_results(args.rows)
    success, _ = run(evals, config, args.output, agents=args.agents, modes=args.modes,
                     rows_file=args.rows, epochs=args.epochs, budget=args.budget,
                     wall_seconds=args.wall_seconds)
    print(f"{len(read_rows(args.output / 'rows.jsonl'))} rows after the run; execution success: {success}")
    return 0


def commit_results(rows, repo, publish):
    if not publish:
        print(f"Dry run: record {len(rows)} rows on {RESULTS_BRANCH}.")
        return
    environment = {**os.environ, "GIT_AUTHOR_NAME": "github-actions[bot]", "GIT_COMMITTER_NAME": "github-actions[bot]",
                   "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                   "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
    # The publisher's checkout can be old. Source always comes from current main.
    base = "refs/remotes/origin/main"
    parents = ["-p", base]
    ref = f"refs/remotes/origin/{RESULTS_BRANCH}"
    has_results = subprocess.run(["git", "show-ref", "--verify", "--quiet", ref]).returncode == 0
    if has_results:
        parents += ["-p", ref]
    with tempfile.TemporaryDirectory() as directory:
        environment["GIT_INDEX_FILE"] = str(Path(directory) / "index")
        row_file = Path(directory) / "rows.jsonl"
        write_rows(row_file, rows)
        command("git", "read-tree", base, env=environment)
        blob = command("git", "hash-object", "-w", row_file, capture_output=True).stdout.strip()
        command("git", "update-index", "--add", "--cacheinfo", f"100644,{blob},results/rows.jsonl", env=environment)
        tree = command("git", "write-tree", capture_output=True, env=environment).stdout.strip()
        previous_tree = command("git", "rev-parse", f"{ref if has_results else base}^{{tree}}", capture_output=True).stdout.strip()
        commit = command("git", "commit-tree", tree, *parents, "-m", "Record eval attempts and log links",
                         capture_output=True, env=environment).stdout.strip() if tree != previous_tree else None
    environment.pop("GIT_INDEX_FILE")
    if commit:
        auth = base64.b64encode(f"x-access-token:{os.environ['GH_TOKEN']}".encode()).decode()
        command("git", "push", "origin", f"{commit}:refs/heads/{RESULTS_BRANCH}",
                env={**environment, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                     "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}"})
        command("git", "update-ref", ref, commit)
    if not (commit or has_results):
        return
    if subprocess.run(["git", "diff", "--quiet", base, ref]).returncode == 0:
        return
    existing = json.loads(command("gh", "pr", "list", "--repo", repo, "--head", RESULTS_BRANCH,
                                  "--base", "main", "--state", "open", "--json", "number", capture_output=True).stdout)
    if not existing:
        command("gh", "pr", "create", "--repo", repo, "--head", RESULTS_BRANCH, "--base", "main",
                "--title", "Record eval results", "--body",
                "Add completed epochs and execution errors. Full logs for scored epochs link to results releases. "
                "Approve the PR checks before merging. Errors retry automatically within the attempt cap on the next run.")


def publish_artifacts(args):
    # Rebuild each attempt from its own logs, even if the run timed out.
    records, rows = [], []
    for output in sorted(args.output.glob("eval-run-*")):
        own_rows = store_rows(output)
        rows = fold_rows(rows, own_rows)
        records.append((output, own_rows))
    if rows:
        commit_results(result_record(rows), args.repo, args.publish)
    status = 0
    for output, own_rows in records:
        try:
            logs = sorted((output / "logs").glob("*.eval"))
            if not logs:
                continue
            commit = read_eval_log(str(logs[0]), header_only=True).eval.revision.commit
            commit = command("git", "rev-parse", commit, capture_output=True).stdout.strip()
            report = publish_logs(output, args.repo, output.name.removeprefix("eval-run-"), commit,
                                  publish=args.publish, rows=own_rows, resume=True)
            print(json.dumps(report, indent=2))
            if own_rows:
                commit_results(result_record(fold_rows(own_rows, read_rows(Path(report["rows_file"])))),
                               args.repo, args.publish)
        except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
            print(f"{output}: publication failed: {error}", file=sys.stderr)
            status = 1
    return status


def checks(args, evals):
    for path in IMAGES.glob("*.compose.yaml"):
        validate_compose(path, stock=True)
    command(sys.executable, "-m", "ethevals.cli", "validate")
    command(sys.executable, "-m", "ethevals.cli", "check", "--output", args.output / "check")
    command(sys.executable, "-m", "pytest", "-q")
    command(sys.executable, "-m", "pytest", "-q", "--run-docker", "-m", "docker",
            "--ignore=inspect-runner/tests/test_agent_docker.py")
    write_hf(evals, args.output / "hf", DEFAULT_REPO, None)
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
    commands = parser.add_subparsers(dest="command", required=True)
    checks_parser = commands.add_parser("checks")
    checks_parser.add_argument("--output", type=Path, required=True)
    run_parser = commands.add_parser("after-merge")
    for name in ("config", "output", "rows"):
        run_parser.add_argument("--" + name, type=Path, required=name == "output",
                                default=Path("results/rows.jsonl") if name == "rows" else None)
    run_parser.add_argument("--evals", nargs="+")
    run_parser.add_argument("--agents", nargs="+")
    run_parser.add_argument("--modes", nargs="+")
    run_parser.add_argument("--epochs", type=positive)
    run_parser.add_argument("--budget", type=float)
    run_parser.add_argument("--wall-seconds", type=float)
    run_parser.add_argument("--restore-results", action="store_true")
    publisher = commands.add_parser("publish-results")
    publisher.add_argument("--output", type=Path, required=True)
    publisher.add_argument("--repo", required=True)
    publisher.add_argument("--publish", action="store_true")
    release_parser = commands.add_parser("release")
    release_parser.add_argument("--output", type=Path, required=True)
    release_parser.add_argument("--hf-repo", default=os.environ.get("ETHEVALS_HF_REPO", DEFAULT_REPO))
    release_parser.add_argument("--license", default=os.environ.get("ETHEVALS_DATASET_LICENSE"))
    release_parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "publish-results":
            return publish_artifacts(args)
        config = load_config(getattr(args, "config", None))
        evals = [load_eval(Path(path), config) for path in getattr(args, "evals", None) or sorted(Path("evals").glob("*/*"))]
        if args.command == "after-merge":
            return after_merge(args, evals, config)
        return {"checks": checks, "release": release}[args.command](args, evals)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ci: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
