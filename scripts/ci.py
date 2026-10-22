"""Local entry points for the workflows. Remote writes require --publish."""
import argparse
import asyncio
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

from ethevals.cli import main as ethevals, parse_args
from ethevals.job_config import load_job
from ethevals.jobs import budget_check, run
from ethevals.hf import DEFAULT_REPO, write_hf
from ethevals.images.tag import BUILD_INPUTS, image_tag
from ethevals.publish import publish_logs
from ethevals.secret_check import RECEIPT, check_output, require_checked, secret_values, stage_artifact
from ethevals.trial_rows import SCHEMA_VERSION, fold_rows, previous_rows, read_rows, write_rows, recover_rows, trial_identity

BASE_BRANCH = "main"
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
    for ref in (f"refs/remotes/origin/{BASE_BRANCH}", f"refs/remotes/origin/{RESULTS_BRANCH}"):
        content = stored_file(ref, "results/rows.jsonl") or ""
        rows = fold_rows(rows, [row for line in content.splitlines() if line.strip()
                               for row in [json.loads(line)] if row.get("schema_version") == SCHEMA_VERSION])
    return fold_rows(rows, own_rows)


def restore_results(rows):
    """Read rows from the pending results PR without executing that branch's code."""
    write_rows(rows, result_record())


def plan_trials(args, run_args):
    argv = ["plan", *run_args, "--output", str(args.output)]
    _, options = parse_args(argv)
    if args.output.exists():
        raise ValueError("Use a fresh output directory for each CI run")
    args.output.mkdir(parents=True)
    rows = args.output / "rows.jsonl"
    if args.restore_results:
        restore_results(rows)
    else:
        write_rows(rows, read_rows(options.rows))
    config = load_job(options.config)
    (args.output / "config.json").write_text(config.model_dump_json() + "\n")
    captured = io.StringIO()
    with redirect_stdout(captured):
        status = ethevals([*argv, "--rows", str(rows)])
    print(captured.getvalue(), end="")
    report = json.loads(captured.getvalue())
    (args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    # A zero CI budget disables even plan-paid trials whose API reserve is zero.
    scheduled, matrix, plan_counts = [], [], {}
    if report["within_budget"] and options.budget and options.budget > 0:
        for row in report["missing"]:
            group = config.agents[row["agent_key"]].name if row["paid_by"] == "plan" else ""
            # GitHub accepts at most 100 pending jobs per concurrency group.
            if len(scheduled) == 256 or group and plan_counts.get(group, 0) == 100:
                continue
            index = len(scheduled)
            item = {**row, "task_path": os.path.relpath(row["task_path"])}
            scheduled.append({"missing": [item], "selected": [trial_identity(row)],
                              "missing_trials": 1, "worst_case_usd": row["worst_case_usd"]})
            matrix.append({"index": index, "task_id": row["task_id"], "agent_key": row["agent_key"],
                           "mode": row["mode"], "trial": row["trial"], "plan_group": group})
            if group:
                plan_counts[group] = plan_counts.get(group, 0) + 1
    (args.output / "trials.json").write_text(json.dumps(scheduled, indent=2) + "\n")
    deferred = len(report["missing"]) - len(scheduled)
    if deferred:
        print(f"Deferred {deferred} trials to a later run.", file=sys.stderr)
    if args.github_output:
        with args.github_output.open("a") as output:
            output.write(f"matrix={json.dumps({'include': matrix}, separators=(',', ':'))}\n")
            output.write(f"scheduled_trials={len(scheduled)}\n")
    return status if options.budget else 0


def run_trial(args):
    scheduled = json.loads((args.plan / "trials.json").read_text())
    if not 0 <= args.index < len(scheduled):
        raise ValueError("Trial index is outside the admitted plan")
    report = scheduled[args.index]
    for item in report["missing"]:
        item["task_path"] = str(Path(item["task_path"]).resolve())
    config = load_job(args.plan / "config.json")
    secrets = secret_values(config, [Path(item["task_path"]) for item in report["missing"]])
    report = budget_check(report, report["worst_case_usd"], required=True)
    previous = previous_rows(args.output, args.plan / "rows.jsonl")
    args.output.mkdir(parents=True, exist_ok=True)
    public = args.output / "public"
    if public.exists():
        import shutil
        shutil.rmtree(public)
    (args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    # Harbor uploads this file itself; it must stay outside the artifact directory.
    with tempfile.TemporaryDirectory(prefix="ethevals-auth-") as directory:
        auth = os.environ.pop("CODEX_AUTH_JSON", None)
        old_path = os.environ.get("CODEX_AUTH_JSON_PATH")
        try:
            if auth:
                path = Path(directory) / "auth.json"
                path.touch(mode=0o600)
                path.write_text(auth)
                os.environ["CODEX_AUTH_JSON_PATH"] = str(path)
            success = asyncio.run(run(report, config, args.output, previous, publication_secrets=secrets))
            print(f"Results rows: {args.output / 'rows.jsonl'}")
            return 0 if success else 1
        finally:
            check_output(args.output, secrets, require_inventory=True)
            stage_artifact(args.output, public)
            if old_path is None:
                os.environ.pop("CODEX_AUTH_JSON_PATH", None)
            else:
                os.environ["CODEX_AUTH_JSON_PATH"] = old_path


def commit_results(rows, repo, publish):
    if not publish:
        print(f"Dry run: record {len(rows)} rows on {RESULTS_BRANCH}.")
        return
    environment = {**os.environ, "GIT_AUTHOR_NAME": "github-actions[bot]", "GIT_COMMITTER_NAME": "github-actions[bot]",
                   "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                   "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
    # The publisher's checkout can be old. Source always comes from the current base branch.
    base = f"refs/remotes/origin/{BASE_BRANCH}"
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
        commit = command("git", "commit-tree", tree, *parents, "-m", "Record trials and trajectory links",
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
                                  "--base", BASE_BRANCH, "--state", "open", "--json", "number", capture_output=True).stdout)
    if not existing:
        command("gh", "pr", "create", "--repo", repo, "--head", RESULTS_BRANCH, "--base", BASE_BRANCH,
                "--title", "Record trial results", "--body",
                "Add completed trials and execution errors. Trajectories and verifier output link to results releases. "
                "Approve the PR checks before merging. Errors retry within the retry cap on the next run.")


def publish_artifacts(args):
    # Rebuild rows at their new download paths, even after an interrupted job.
    rows = []
    combined = args.output / "combined"
    for output in sorted(args.output.glob("trial-run-*")):
        for folder in sorted((output / "jobs").glob("*")):
            receipt = folder / RECEIPT
            if not receipt.is_file() or not json.loads(receipt.read_text()).get("withheld"):
                require_checked(folder)
        rows = fold_rows(rows, recover_rows(output))
    if not rows:
        return 0
    try:
        report = publish_logs(combined, args.repo, args.run_id, args.commit, rows=rows)
        linked = result_record(report["rows"])
        write_rows(combined / "rows.jsonl", linked)
        commit_results(linked, args.repo, args.publish)
        if args.publish:
            report = publish_logs(combined, args.repo, args.run_id, args.commit,
                                  publish=True, rows=rows, resume=True)
        (combined / "release.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"{combined}: publication failed: {error}", file=sys.stderr)
        return 1
    return 0


def checks(args):
    images(argparse.Namespace(publish=False))
    command(sys.executable, "-m", "ethevals.cli", "free-check", "--output", args.output / "harbor")
    command(sys.executable, "-m", "pytest", "-q")
    command(sys.executable, "-m", "pytest", "-q", "--run-docker", "-m", "docker")
    for task in ("test", "typecheck", "lint", "build"):
        command("pnpm", task, cwd="site")
    return 0


def hf_get(repo, path):
    token = os.environ.get("HF_TOKEN")
    request = Request(f"https://huggingface.co/api/datasets/{repo}/{path}",
                      headers={"Authorization": f"Bearer {token}"} if token else {})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def hf_tag(sha):
    return f"gh-{sha[:7]}"


def images(args):
    directory = Path(__file__).resolve().parents[1] / "runner/ethevals/images"
    tags = []
    for name, inputs in BUILD_INPUTS.items():
        dockerfile = inputs[0]
        tag = "ghcr.io/buidlguidl/" + image_tag(directory, name)
        tags.append(tag)
        if args.publish:
            command("docker", "buildx", "build", "--platform", "linux/amd64,linux/arm64", "--push",
                    "--file", directory / dockerfile, "--tag", tag, directory)
        else:
            command("docker", "build", "--file", directory / dockerfile, "--tag", tag, directory)
    if args.publish:
        # GHCR starts new packages as private. Do not publish tasks until readers can pull them.
        with tempfile.TemporaryDirectory(prefix="ethevals-public-image-") as anonymous:
            for tag in tags:
                command("docker", "--config", anonymous, "manifest", "inspect", tag, stdout=subprocess.DEVNULL)
    return 0


def release(args):
    if not args.license:
        raise ValueError("Choose the dataset license before a release")
    paths = sorted(path.parent for path in Path("tasks").rglob("task.toml"))
    print(json.dumps(write_hf(paths, args.output, args.hf_repo, args.license), indent=2))
    commit = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    tag = hf_tag(commit)
    message = f"ETH Evals from BuidlGuidl/ethevals@{commit}"
    command_line = ["hf", "upload", args.hf_repo, str(args.output), ".", "--repo-type", "dataset",
                    "--commit-message", message, "--delete", "tasks/*", "--delete", "data/*"]
    if args.publish:
        command(*command_line)
        head, tags = hf_get(args.hf_repo, "commits/main")[0], hf_get(args.hf_repo, "refs")["tags"]
        if head["title"] == message and tag not in {ref["name"] for ref in tags}:
            command("hf", "repo", "tag", "create", args.hf_repo, tag, "--repo-type", "dataset", "--revision", head["id"])
    else:
        print(json.dumps({"dry_run": True, "command": command_line, "tag": tag}))
    return 0


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    checks_parser = commands.add_parser("checks")
    checks_parser.add_argument("--output", type=Path, required=True)
    builder = commands.add_parser("images", help="Build shared images with the GHCR tags used by task folders.")
    builder.add_argument("--publish", action="store_true", help="Push multi-architecture images to GHCR.")
    planner = commands.add_parser("plan-trials")
    planner.add_argument("--output", type=Path, required=True)
    planner.add_argument("--restore-results", action="store_true")
    planner.add_argument("--github-output", type=Path)
    trial = commands.add_parser("run-trial")
    trial.add_argument("--plan", type=Path, required=True)
    trial.add_argument("--index", type=int, required=True)
    trial.add_argument("--output", type=Path, required=True)
    publisher = commands.add_parser("publish-results")
    publisher.add_argument("--output", type=Path, required=True)
    publisher.add_argument("--repo", required=True)
    publisher.add_argument("--publish", action="store_true")
    publisher.add_argument("--run-id", required=True)
    publisher.add_argument("--commit", required=True)
    release_parser = commands.add_parser("release")
    release_parser.add_argument("--output", type=Path, required=True)
    release_parser.add_argument("--hf-repo", default=DEFAULT_REPO)
    release_parser.add_argument("--license")
    release_parser.add_argument("--publish", action="store_true")
    args, run_args = parser.parse_known_args()
    try:
        if args.command == "plan-trials":
            return plan_trials(args, run_args)
        args = parser.parse_args()
        if args.command == "run-trial":
            return run_trial(args)
        if args.command == "images":
            return images(args)
        if args.command == "publish-results":
            return publish_artifacts(args)
        if args.command == "checks":
            return checks(args)
        return release(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ci: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
