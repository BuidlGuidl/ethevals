"""Local entry points for the workflows. Remote writes require --publish."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import io
import zipfile
from datetime import datetime, timedelta, timezone

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
    return subprocess.run(list(map(str, args)), check=True, text=kwargs.pop("text", True), **kwargs)


def stored_file(ref, path):
    result = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    if result.returncode:
        return None
    return result.stdout


def result_record(own_rows=(), own_receipts=None):
    rows, saved = [], {}
    for ref in ("HEAD", "refs/remotes/origin/main", f"refs/remotes/origin/{RESULTS_BRANCH}"):
        content = stored_file(ref, "results/rows.jsonl") or ""
        rows = fold_rows(rows, [json.loads(line) for line in content.splitlines() if line.strip()])
        saved.update(json.loads(stored_file(ref, RECEIPTS) or "{}"))
    saved.update(own_receipts or {})
    return fold_rows(rows, own_rows), saved


def restore_results(rows):
    """Read rows from the pending results PR without executing that branch's code."""
    write_rows(rows, result_record()[0])


def require_recorded_runs(repo):
    saved = result_record()[1]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    missing = []
    page = 1
    while True:
        artifacts = json.loads(command("gh", "api",
            f"repos/{repo}/actions/artifacts?per_page=100&page={page}", capture_output=True).stdout)["artifacts"]
        for artifact in artifacts:
            if artifact["created_at"] < cutoff:
                break
            if not artifact["name"].startswith("eval-run-"):
                continue
            identity = artifact["name"].removeprefix("eval-run-")
            if identity in saved:
                continue
            if artifact["expired"]:
                missing.append(identity)
                continue
            archive = command("gh", "api", f"repos/{repo}/actions/artifacts/{artifact['id']}/zip",
                              capture_output=True, text=False).stdout
            with zipfile.ZipFile(io.BytesIO(archive)) as contents:
                markers = [name for name in contents.namelist() if name.endswith("/paid-started.json") or name == "paid-started.json"]
                for name in markers:
                    marker = json.loads(contents.read(name))
                    if marker["run_id"] not in saved:
                        missing.append(marker["run_id"])
        if len(artifacts) < 100 or artifacts[-1]["created_at"] < cutoff:
            break
        page += 1
    if missing:
        raise ValueError("Recover unrecorded eval run artifacts before paid work: " + ", ".join(missing))


def after_merge(args, evals, config):
    if args.output.exists():
        raise ValueError("Use a fresh output directory for each CI run")
    args.output.mkdir(parents=True)
    (args.output / "execution.json").write_text(json.dumps({"success": False}) + "\n")
    if args.restore_results:
        restore_results(args.rows)
    def before_paid():
        if os.environ.get("GITHUB_ACTIONS") == "true":
            marker = {"run_id": f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}",
                      "commit": command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()}
            (args.output / "paid-started.json").write_text(json.dumps(marker) + "\n")
    success, _ = run(evals, config, args.output, models=args.models, modes=args.modes, answer=args.answer,
                     rows_file=args.rows, epochs=args.epochs, budget=args.budget,
                     wall_seconds=args.wall_seconds, before_paid=before_paid)
    (args.output / "execution.json").write_text(json.dumps({"success": success}) + "\n")
    print(f"{len(read_rows(args.output / 'rows.jsonl'))} rows after the run; execution success: {success}")
    return 0


def commit_results(rows, saved, repo, publish):
    if not publish:
        print(f"Dry run: record {len(rows)} rows and {len(saved)} receipts on {RESULTS_BRANCH}.")
        return
    environment = {**os.environ, "GIT_AUTHOR_NAME": "github-actions[bot]", "GIT_COMMITTER_NAME": "github-actions[bot]",
                   "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                   "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
    # The publisher's checkout can be old. Source always comes from current main.
    base = "refs/remotes/origin/main"
    if subprocess.run(["git", "show-ref", "--verify", "--quiet", base]).returncode:
        base = "HEAD"
    parents = ["-p", base]
    ref = f"refs/remotes/origin/{RESULTS_BRANCH}"
    has_results = subprocess.run(["git", "show-ref", "--verify", "--quiet", ref]).returncode == 0
    if has_results:
        parents += ["-p", ref]
    with tempfile.TemporaryDirectory() as directory:
        environment["GIT_INDEX_FILE"] = str(Path(directory) / "index")
        row_file, receipt_file = Path(directory) / "rows.jsonl", Path(directory) / "runs.json"
        write_rows(row_file, rows)
        receipt_file.write_text(json.dumps(saved, sort_keys=True) + "\n")
        command("git", "read-tree", base, env=environment)
        for source, destination in [(row_file, "results/rows.jsonl"), (receipt_file, "results/runs.json")]:
            if source.exists():
                blob = command("git", "hash-object", "-w", source, capture_output=True).stdout.strip()
                command("git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{destination}", env=environment)
        tree = command("git", "write-tree", capture_output=True, env=environment).stdout.strip()
        previous_tree = command("git", "rev-parse", f"{ref if has_results else base}^{{tree}}", capture_output=True).stdout.strip()
        commit = command("git", "commit-tree", tree, *parents, "-m", "Record eval attempts and log links",
                         capture_output=True, env=environment).stdout.strip() if tree != previous_tree else None
    environment.pop("GIT_INDEX_FILE")
    if not commit:
        return
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


def publish_results(args):
    # Logs are the recovery source even if execution never returned or exported rows.
    if not args.output.is_dir():
        raise ValueError("Recover the run artifact before recording its receipt")
    marker = args.output / "paid-started.json"
    if not marker.exists():
        recovered = sorted(args.output.rglob("paid-started.json"))
        if recovered:
            return max(publish_results(argparse.Namespace(**{**vars(args), "output": path.parent})) for path in recovered)
        print("No paid work began; no receipt or results PR.")
        return 0
    identity = json.loads(marker.read_text())
    run_id, commit = identity["run_id"], identity["commit"]
    export_rows(args.output)
    own_rows = store_rows(args.output)
    record = result_record(own_rows, {run_id: {"commit": commit}})
    commit_results(*record, args.repo, args.publish)
    report = publish_logs(args.output, args.repo, run_id, commit,
                          current_hashes={row["eval_id"]: row["eval_hash"] for row in own_rows},
                          publish=args.publish, rows=own_rows, resume=True)
    print(json.dumps(report, indent=2))
    commit_results(*result_record(fold_rows(own_rows, read_rows(Path(report["rows_file"]))),
                                  {run_id: {"commit": commit}}), args.repo, args.publish)
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
    parser.add_argument("command", choices=["checks", "after-merge", "publish-results", "release", "recovery-check", "accept-loss"])
    parser.add_argument("--output", type=Path)
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
    parser.add_argument("--reason")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--hf-repo", default=DEFAULT_REPO)
    parser.add_argument("--license")
    args = parser.parse_args()
    if args.epochs is not None and args.epochs < 1:
        parser.error("--epochs must be at least 1")
    if args.command in {"publish-results", "recovery-check", "accept-loss"} and not args.repo:
        parser.error("This command requires --repo")
    if args.command not in {"recovery-check", "accept-loss"} and not args.output:
        parser.error("This command requires --output")
    try:
        if args.command == "recovery-check":
            require_recorded_runs(args.repo)
            return 0
        if args.command == "accept-loss":
            if not args.run_id or not args.reason or not args.reason.strip():
                raise ValueError("accept-loss requires --run-id and --reason")
            commit_results(*result_record(own_receipts={args.run_id: {"accepted_loss": args.reason}}), args.repo, args.publish)
            return 0
        if args.command == "publish-results":
            return publish_results(args)
        config = load_config(args.config)
        evals = [load_eval(Path(path), config) for path in args.evals or sorted(Path("evals").glob("*/*"))]
        if args.command == "after-merge":
            return after_merge(args, evals, config)
        return {"checks": checks, "release": release}[args.command](args, evals)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ci: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
