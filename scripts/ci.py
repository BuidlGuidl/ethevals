"""Local entry points for the workflows. Remote writes require --publish."""
import argparse
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

from ethevals.cli import main as ethevals, parse_args
from ethevals.config import load_config
from ethevals.hf import DEFAULT_REPO, write_hf
from ethevals.loader import load_eval
from ethevals.publish import publish_logs
from ethevals.rows import fold_rows, read_rows, write_rows, store_rows

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
        rows = fold_rows(rows, [json.loads(line) for line in content.splitlines() if line.strip()])
    return fold_rows(rows, own_rows)


def restore_results(rows):
    """Read rows from the pending results PR without executing that branch's code."""
    write_rows(rows, result_record())


def plan_epochs(args, run_args):
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
    config = load_config(options.config, effort=options.effort)
    (args.output / "config.json").write_text(config.model_dump_json() + "\n")
    captured = io.StringIO()
    with redirect_stdout(captured):
        status = ethevals([*argv, "--rows", str(rows)])
    print(captured.getvalue(), end="")
    report = json.loads(captured.getvalue())
    (args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    if status:
        return status
    missing = report["missing"][:256]
    matrix = {"include": [{"index": index, **{key: row[key] for key in
               ("eval_id", "actor_key", "mode", "epoch", "worst_case_usd")}} for index, row in enumerate(missing)]}
    if len(report["missing"]) > len(missing):
        print(f"Deferred {len(report['missing']) - len(missing)} epochs to a later run.", file=sys.stderr)
    if args.github_output:
        with args.github_output.open("a") as output:
            output.write(f"matrix={json.dumps(matrix, separators=(',', ':'))}\n")
            output.write(f"missing_epochs={report['missing_epochs']}\n")
    return 0


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
                                  "--base", BASE_BRANCH, "--state", "open", "--json", "number", capture_output=True).stdout)
    if not existing:
        command("gh", "pr", "create", "--repo", repo, "--head", RESULTS_BRANCH, "--base", BASE_BRANCH,
                "--title", "Record eval results", "--body",
                "Add completed epochs and execution errors. Full logs for scored epochs link to results releases. "
                "Approve the PR checks before merging. Errors retry automatically within the attempt cap on the next run.")


def publish_artifacts(args):
    # Rebuild each attempt from its own logs, even if the run timed out.
    rows = []
    combined = args.output / "combined"
    logs = combined / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    for output in sorted(args.output.glob("eval-run-*")):
        own_rows = store_rows(output)
        rows = fold_rows(rows, own_rows)
        for source in sorted((output / "logs").glob("*.eval")):
            shutil.copyfile(source, logs / source.name)
    if not rows:
        return 0
    linked = [{**row, "log_url": row.get("log_url") or
               f"https://github.com/{args.repo}/releases/download/results-{args.run_id}/{Path(row['log_file']).name}"}
              if row["status"] in {"passed", "failed"} else row for row in rows]
    commit_results(result_record(linked), args.repo, args.publish)
    try:
        report = publish_logs(combined, args.repo, args.run_id, args.commit,
                              publish=args.publish, rows=rows, resume=True)
        print(json.dumps(report, indent=2))
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"{combined}: publication failed: {error}", file=sys.stderr)
        return 1
    return 0


def checks(args, evals):
    command(sys.executable, "-m", "ethevals.cli", "validate")
    command(sys.executable, "-m", "ethevals.cli", "check", "--output", args.output / "check")
    command(sys.executable, "-m", "pytest", "-q")
    command(sys.executable, "-m", "pytest", "-q", "--run-docker", "-m", "docker",
            "--ignore=inspect-runner/tests/test_agents_docker.py")
    write_hf(evals, args.output / "hf", DEFAULT_REPO, None)
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


def release(args, evals):
    if not args.license:
        raise ValueError("Choose the dataset license before a release")
    print(json.dumps(write_hf(evals, args.output, args.hf_repo, args.license), indent=2))
    commit = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    tag = hf_tag(commit)
    message = f"ETH Evals from BuidlGuidl/ethevals@{commit}"
    command_line = ["hf", "upload", args.hf_repo, str(args.output), ".", "--repo-type", "dataset",
                    "--commit-message", message]
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
    planner = commands.add_parser("plan-epochs")
    planner.add_argument("--output", type=Path, required=True)
    planner.add_argument("--restore-results", action="store_true")
    planner.add_argument("--github-output", type=Path)
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
        if args.command == "plan-epochs":
            return plan_epochs(args, run_args)
        args = parser.parse_args()
        if args.command == "publish-results":
            return publish_artifacts(args)
        config = load_config()
        evals = [load_eval(path, config) for path in sorted(Path("evals").glob("*/*"))]
        return {"checks": checks, "release": release}[args.command](args, evals)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"ci: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
