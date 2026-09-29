"""Local entry points for the workflows. Remote writes require --publish."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ethevals.config import load_config
from ethevals.hf import DEFAULT_REPO, write_hf
from ethevals.hf_proof import prove
from ethevals.loader import load_eval
from ethevals.publish import publish_logs
from ethevals.rows import fold_rows, read_rows, write_rows, export_rows, store_rows
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
    (args.output / "execution.json").write_text(json.dumps({"success": False}) + "\n")
    if args.restore_results:
        restore_results(args.rows)
    success, _ = run(evals, config, args.output, models=args.models, modes=args.modes, answer=args.answer,
                     rows_file=args.rows, epochs=args.epochs, budget=args.budget,
                     wall_seconds=args.wall_seconds)
    (args.output / "execution.json").write_text(json.dumps({"success": success}) + "\n")
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
        export_rows(output)
        own_rows = store_rows(output)
        rows = fold_rows(rows, own_rows)
        records.append((output, own_rows))
    if rows:
        commit_results(result_record(rows), args.repo, args.publish)
    status = 0
    for output, own_rows in records:
        try:
            report = publish_logs(output, args.repo, output.name.removeprefix("eval-run-"), args.commit,
                                  current_hashes={row["eval_id"]: row["eval_hash"] for row in own_rows},
                                  publish=args.publish, rows=own_rows, resume=True)
            print(json.dumps(report, indent=2))
            if own_rows:
                commit_results(result_record(fold_rows(own_rows, read_rows(Path(report["rows_file"])))),
                               args.repo, args.publish)
            execution = output / "execution.json"
            if execution.exists() and not json.loads(execution.read_text())["success"]:
                print("Results retained. Some evals have execution or discovery errors.", file=sys.stderr)
                status = 1
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
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument("--output", type=Path)
    options.add_argument("--config", type=Path)
    options.add_argument("--evals", nargs="+")
    options.add_argument("--models", nargs="+")
    options.add_argument("--modes", nargs="+", default=["vanilla", "internet"])
    options.add_argument("--epochs", type=int)
    options.add_argument("--answer", choices=["reference", "empty", "default"])
    options.add_argument("--budget", type=float, default=0)
    options.add_argument("--wall-seconds", type=float, default=16200)
    options.add_argument("--restore-results", action="store_true")
    options.add_argument("--repo")
    options.add_argument("--commit")
    options.add_argument("--publish", action="store_true")
    options.add_argument("--hf-repo", default=DEFAULT_REPO)
    options.add_argument("--license")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("checks", "after-merge", "publish-results", "release"):
        command_parser = commands.add_parser(name, parents=[options])
        if name == "after-merge":
            command_parser.add_argument("--rows", type=Path, default=Path("results/rows.jsonl"))
    args = parser.parse_args()
    if args.epochs is not None and args.epochs < 1:
        parser.error("--epochs must be at least 1")
    if args.command == "publish-results" and not (args.repo and args.commit):
        parser.error("This command requires --repo and --commit")
    if not args.output:
        parser.error("This command requires --output")
    try:
        if args.command == "publish-results":
            return publish_artifacts(args)
        config = load_config(args.config)
        evals = [load_eval(Path(path), config) for path in args.evals or sorted(Path("evals").glob("*/*"))]
        if args.command == "after-merge":
            return after_merge(args, evals, config)
        return {"checks": checks, "release": release}[args.command](args, evals)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ci: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
