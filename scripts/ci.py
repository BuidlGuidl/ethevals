"""Local entry points for the workflows. Remote writes require --publish."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import re

from ethevals.config import load_config
from ethevals.hf import DEFAULT_REPO, write_hf
from ethevals.hf_proof import prove
from ethevals.loader import load_eval
from ethevals.publish import publish_logs
from ethevals.rows import fold_rows, read_rows, write_rows, export_rows, store_rows
from ethevals.runner import run
from ethevals.actors import select_actors
from ethevals.planning import plan, budget_check
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
    for ref in ("refs/remotes/origin/main", f"refs/remotes/origin/{RESULTS_BRANCH}"):
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
    missing = []
    for page in range(1, 101):
        artifacts = json.loads(command("gh", "api",
            f"repos/{repo}/actions/artifacts?per_page=100&page={page}", capture_output=True).stdout)["artifacts"]
        for artifact in artifacts:
            if not artifact["name"].startswith("paid-"):
                continue
            identity = artifact["name"].removeprefix("paid-")
            if identity in saved:
                continue
            missing.append(identity)
        if len(artifacts) < 100:
            break
    else:
        raise ValueError("Recovery scan exceeded 10000 artifacts. Review artifact retention before paid work.")
    if missing:
        raise ValueError("Recover unrecorded paid attempts before paid work: " + ", ".join(sorted(set(missing))))


def after_merge(args, evals, config):
    if args.output.exists():
        raise ValueError("Use a fresh output directory for each CI run")
    args.output.mkdir(parents=True)
    if not args.answer and os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("ETHEVALS_PAID_MARKER"):
        (args.output / "paid-started.json").write_bytes(Path(os.environ["ETHEVALS_PAID_MARKER"]).read_bytes())
    (args.output / "execution.json").write_text(json.dumps({"success": False}) + "\n")
    if args.restore_results:
        restore_results(args.rows)
    def before_paid():
        if os.environ.get("GITHUB_ACTIONS") == "true":
            marker = {"run_id": f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}",
                      "commit": command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()}
            reserved = Path(os.environ["ETHEVALS_PAID_MARKER"])
            if json.loads(reserved.read_text()) != marker:
                raise ValueError("Uploaded paid marker does not match this attempt")
            (args.output / "paid-started.json").write_text(json.dumps(marker) + "\n")
    success, _ = run(evals, config, args.output, models=args.models, modes=args.modes, answer=args.answer,
                     rows_file=args.rows, epochs=args.epochs, budget=args.budget,
                     wall_seconds=args.wall_seconds, before_paid=before_paid)
    (args.output / "execution.json").write_text(json.dumps({"success": success}) + "\n")
    print(f"{len(read_rows(args.output / 'rows.jsonl'))} rows after the run; execution success: {success}")
    return 0


def plan_paid(args, evals, config):
    """Reserve an attempt before the workflow uploads its small paid marker."""
    if args.restore_results:
        restore_results(args.rows)
    players, _ = select_actors(config, args.models, args.modes, planning=True)
    report = budget_check(plan(evals, config, players, read_rows(args.rows), epochs=args.epochs,
                               wall_seconds=args.wall_seconds).report, args.budget, required=True)
    if not report["within_budget"]:
        raise ValueError("Budget exceeded. No player or grader ran.")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    ready = bool(report["missing"])
    if not ready and report["deferred_epochs"]:
        raise ValueError(f"No epochs admitted; {report['deferred_epochs']} remain deferred. Increase --wall-seconds.")
    if ready:
        marker = {"run_id": f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}",
                  "commit": command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()}
        (args.output / "paid-started.json").write_text(json.dumps(marker) + "\n")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        stream.write(f"ready={str(ready).lower()}\n")
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


def artifact_record(output):
    marker = json.loads((output / "paid-started.json").read_text())
    export_rows(output)
    return store_rows(output), {marker["run_id"]: {"commit": marker["commit"]}}


def publish_results(output, own_rows, receipt, repo, publish):
    """Upload one recorded attempt and attach its successful log links."""
    run_id, identity = next(iter(receipt.items()))
    report = publish_logs(output, repo, run_id, identity["commit"],
                          current_hashes={row["eval_id"]: row["eval_hash"] for row in own_rows},
                          publish=publish, rows=own_rows, resume=True)
    print(json.dumps(report, indent=2))
    commit_results(*result_record(fold_rows(own_rows, read_rows(Path(report["rows_file"]))), receipt), repo, publish)
    execution = output / "execution.json"
    if execution.exists() and not json.loads(execution.read_text())["success"]:
        print("Results retained. Some evals have execution or discovery errors.", file=sys.stderr)
        return 1
    return 0


def publish_artifacts(args):
    # Logs are the recovery source even if execution never returned or exported rows.
    if not args.output.is_dir():
        raise ValueError("Recover the run artifact before recording its receipt")
    markers = list(args.output.rglob("paid-started.json"))
    if not markers:
        print("No paid work began; no receipt or results PR.")
        return 0
    rows, receipts, records = [], {}, []
    for marker in markers:
        own_rows, receipt = artifact_record(marker.parent)
        rows = fold_rows(rows, own_rows)
        receipts.update(receipt)
        records.append((marker.parent, own_rows, receipt))
    commit_results(*result_record(rows, receipts), args.repo, args.publish)
    status = 0
    for output, own_rows, receipt in sorted(records, key=lambda record: tuple(map(int, next(iter(record[2])).split("-")))):
        try:
            status = max(status, publish_results(output, own_rows, receipt, args.repo, args.publish))
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
    options.add_argument("--run-id")
    options.add_argument("--reason")
    options.add_argument("--publish", action="store_true")
    options.add_argument("--hf-repo", default=DEFAULT_REPO)
    options.add_argument("--license")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("checks", "plan-paid", "after-merge", "publish-results", "release", "recovery-check", "accept-loss"):
        command_parser = commands.add_parser(name, parents=[options])
        if name in {"plan-paid", "after-merge"}:
            command_parser.add_argument("--rows", type=Path, default=Path("results/rows.jsonl"))
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
            if not re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", args.run_id):
                raise ValueError("--run-id must use RUN-ATTEMPT with positive integers")
            commit_results(*result_record(own_receipts={args.run_id: {"accepted_loss": args.reason}}), args.repo, args.publish)
            return 0
        if args.command == "publish-results":
            return publish_artifacts(args)
        config = load_config(args.config)
        evals = [load_eval(Path(path), config) for path in args.evals or sorted(Path("evals").glob("*/*"))]
        if args.command == "after-merge":
            return after_merge(args, evals, config)
        if args.command == "plan-paid":
            return plan_paid(args, evals, config)
        return {"checks": checks, "release": release}[args.command](args, evals)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ci: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
