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
RECEIPTS = Path("results/runs.json")


def command(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, text=True, **kwargs)


def stored_file(ref, path):
    result = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    if result.returncode:
        return None
    return result.stdout


def receipts():
    return json.loads(RECEIPTS.read_text()) if RECEIPTS.exists() else {}


def restore_results(rows):
    """Read rows from the pending results PR without executing that branch's code."""
    ref = f"refs/remotes/origin/{RESULTS_BRANCH}"
    if subprocess.run(["git", "show-ref", "--verify", "--quiet", ref]).returncode == 0:
        content = command("git", "show", f"{ref}:results/rows.jsonl", capture_output=True).stdout
        pending = [json.loads(line) for line in content.splitlines() if line.strip()]
        write_rows(rows, fold_rows(read_rows(rows), pending))
        saved = receipts()
        saved.update(json.loads(stored_file(ref, RECEIPTS) or "{}"))
        RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
        RECEIPTS.write_text(json.dumps(saved, sort_keys=True) + "\n")


def require_recorded_runs(repo, run_id, run_attempt):
    saved = receipts()
    pages = command("gh", "api", "--paginate", "--slurp",
                    f"repos/{repo}/actions/workflows/results.yml/runs?branch=main&per_page=100",
                    capture_output=True).stdout
    missing = []
    for page in json.loads(pages):
        for previous in page["workflow_runs"]:
            if str(previous["id"]) == str(run_id) or previous.get("status") in {"queued", "waiting", "requested", "pending"}:
                continue
            for attempt in range(1, previous["run_attempt"] + 1):
                identity = f"{previous['id']}-{attempt}"
                if identity not in saved:
                    if previous.get("conclusion") in {"cancelled", "skipped"}:
                        jobs = json.loads(command("gh", "api", "--paginate", "--slurp",
                            f"repos/{repo}/actions/runs/{previous['id']}/attempts/{attempt}/jobs?per_page=100",
                            capture_output=True).stdout)
                        if not any(step.get("started_at") and step.get("conclusion") != "skipped"
                                   for page in jobs for job in page["jobs"] for step in job.get("steps", [])
                                   if step["name"] == "Plan and run missing epochs"):
                            continue
                    missing.append(identity)
    missing.extend(f"{run_id}-{attempt}" for attempt in range(1, int(run_attempt))
                   if f"{run_id}-{attempt}" not in saved)
    if missing:
        raise ValueError("Recover unrecorded eval run artifacts before paid work: " + ", ".join(missing))


def after_merge(args, evals, config):
    if args.output.exists():
        raise ValueError("Use a fresh output directory for each CI run")
    if args.restore_results:
        restore_results(args.rows)
    def before_paid():
        if os.environ.get("GITHUB_ACTIONS") == "true":
            require_recorded_runs(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"],
                                  os.environ["GITHUB_RUN_ATTEMPT"])
    success, _ = run(evals, config, args.output, models=args.models, modes=args.modes, answer=args.answer,
                     rows_file=args.rows, epochs=args.epochs, budget=args.budget,
                     wall_seconds=args.wall_seconds, before_paid=before_paid)
    (args.output / "execution.json").write_text(json.dumps({"success": success}) + "\n")
    print(f"{len(read_rows(args.output / 'rows.jsonl'))} rows after the run; execution success: {success}")
    return 0


def results_pr(rows, repo, publish):
    if not publish:
        print(f"Dry run: commit {rows} to {RESULTS_BRANCH} and open a results PR against main.")
        return
    environment = {**os.environ, "GIT_AUTHOR_NAME": "github-actions[bot]", "GIT_COMMITTER_NAME": "github-actions[bot]",
                   "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                   "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
    # The publisher's checkout can be old. Source always comes from current main.
    base = "refs/remotes/origin/main"
    if subprocess.run(["git", "show-ref", "--verify", "--quiet", base]).returncode:
        base = "HEAD"
    current = [json.loads(line) for line in (stored_file(base, "results/rows.jsonl") or "").splitlines() if line.strip()]
    write_rows(rows, fold_rows(current, read_rows(rows)))
    saved = json.loads(stored_file(base, RECEIPTS) or "{}")
    saved.update(receipts())
    RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
    RECEIPTS.write_text(json.dumps(saved, sort_keys=True) + "\n")
    restore_results(rows)
    parents = ["-p", base]
    ref = f"refs/remotes/origin/{RESULTS_BRANCH}"
    has_results = subprocess.run(["git", "show-ref", "--verify", "--quiet", ref]).returncode == 0
    if has_results:
        parents += ["-p", ref]
    with tempfile.TemporaryDirectory() as directory:
        environment["GIT_INDEX_FILE"] = str(Path(directory) / "index")
        command("git", "read-tree", base, env=environment)
        for source, destination in [(rows, "results/rows.jsonl"), (RECEIPTS, "results/runs.json")]:
            if source.exists():
                blob = command("git", "hash-object", "-w", source, capture_output=True).stdout.strip()
                command("git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{destination}", env=environment)
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
    existing = json.loads(command("gh", "pr", "list", "--repo", repo, "--head", RESULTS_BRANCH,
                                  "--base", "main", "--state", "open", "--json", "number", capture_output=True).stdout)
    if not existing:
        command("gh", "pr", "create", "--repo", repo, "--head", RESULTS_BRANCH, "--base", "main",
                "--title", "Record eval results", "--body",
                "Add completed epochs and execution errors. Full logs for scored epochs link to results releases. "
                "Approve the PR checks before merging. Errors retry automatically within the attempt cap on the next run.")


def publish_results(args, evals):
    # Logs are the recovery source even if execution never returned or exported rows.
    if not args.output.is_dir():
        raise ValueError("Recover the run artifact before recording its receipt")
    export_rows(args.output)
    own_rows = store_rows(args.output)
    if args.publish:
        restore_results(args.rows)
        write_rows(args.rows, fold_rows(read_rows(args.rows), own_rows))
        saved = receipts()
        saved[args.run_id] = {"commit": args.commit}
        RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
        RECEIPTS.write_text(json.dumps(saved, sort_keys=True) + "\n")
        if args.open_pr:
            results_pr(args.rows, args.repo, True)
    report = publish_logs(args.output, args.repo, args.run_id, args.commit,
                          current_hashes={row["eval_id"]: row["eval_hash"] for row in own_rows},
                          publish=args.publish, rows=own_rows, resume=True)
    print(json.dumps(report, indent=2))
    if args.publish:
        write_rows(args.rows, fold_rows(read_rows(args.rows), own_rows,
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
    parser.add_argument("--wall-seconds", type=float, default=16200)
    parser.add_argument("--restore-results", action="store_true")
    parser.add_argument("--repo")
    parser.add_argument("--run-id")
    parser.add_argument("--commit")
    parser.add_argument("--open-pr", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--hf-repo", default=DEFAULT_REPO)
    parser.add_argument("--license")
    args = parser.parse_args()
    if args.epochs is not None and args.epochs < 1:
        parser.error("--epochs must be at least 1")
    if args.command == "publish-results" and not all((args.repo, args.run_id, args.commit)):
        parser.error("publish-results requires --repo, --run-id, and --commit")
    try:
        config = load_config(args.config)
        evals = [load_eval(Path(path), config) for path in args.evals or sorted(Path("evals").glob("*/*"))]
        if args.command == "after-merge":
            return after_merge(args, evals, config)
        return {"checks": checks, "publish-results": publish_results, "release": release}[args.command](args, evals)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ci: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
