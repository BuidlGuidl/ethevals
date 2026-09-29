"""Regression cases from the final full review."""
import argparse
import json
import subprocess

import pytest
from inspect_ai import eval
from inspect_ai.util import ExecResult

from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.rows import read_rows, results_rows
from ethevals.runner import run
from test_ci import ROOT, ci, cli
from test_contracts import scoring_case


@pytest.mark.parametrize("local_oom,status", [(True, "failed"), (False, "error")])
def test_agent_failure_exports_memory_cause(scoring_case, monkeypatch, local_oom, status):
    from ethevals import agents
    config = load_config()

    class Box:
        reads = 0
        async def exec(self, command, **kwargs):
            self.reads += 1
            return ExecResult(success=True, returncode=0, stdout=(
                "oom 4\noom_kill 4\n" if self.reads == 1 else
                f"oom {5 if local_oom else 4}\noom_kill 5\n"), stderr="")

    async def killed(state, generate):
        raise RuntimeError("Error executing agent 137: Killed")

    monkeypatch.setitem(agents.AGENTS, "proof", agents.Harness(lambda *a, **kw: killed, "proof"))
    monkeypatch.setattr(agents, "sandbox", lambda name: box)
    box = Box()
    scoring_case["task"].solver = agents.internet_solver("proof", config, config.models["opus"])
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"]) == (status, False if local_oom else None)
    if local_oom:
        assert {check["reason"] for check in row["checks"].values()} == {"Agent exceeded its container memory limit."}
    else:
        assert "Error executing agent 137" in row["error_reason"]


def test_earlier_chain_oom_does_not_change_wrapper_failure(monkeypatch):
    import anyio
    from ethevals.check_script import script_result

    class Box:
        async def exec(self, command, **kwargs):
            if "/sys/fs/cgroup/memory.events" in command:
                return ExecResult(success=True, returncode=0, stdout="oom 8\noom_kill 3\n", stderr="")
            code = 125 if "/usr/bin/timeout" in command else 0
            return ExecResult(success=code == 0, returncode=code, stdout="", stderr="")

    with pytest.raises(RuntimeError, match="Cannot capture check script output"):
        anyio.run(script_result, "check", Box())


def test_budget_below_cheapest_group_stops_before_preparation(tmp_path, monkeypatch):
    config = load_config()
    evaluation = load_eval(ROOT / "evals/building/erc20-points-token", config)
    monkeypatch.setattr("ethevals.runner.prepare_compose", lambda *a: pytest.fail("Preparation ran"))
    with pytest.raises(ValueError, match="Budget exceeded"):
        run([evaluation], config, tmp_path, budget=1, epochs=1, modes=["internet"])
    report = json.loads((tmp_path / "plan.json").read_text())
    assert (report["cheapest_group_usd"], report["missing_epochs"]) == (237.8304, 4)


def test_all_artifact_receipts_precede_any_upload(tmp_path, monkeypatch):
    config = load_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    first, second = tmp_path / "12-2", tmp_path / "12-10"
    run([evaluation], config, first, answer="reference", epochs=1)
    run([evaluation], config, second, answer="reference", epochs=2, rows_file=first / "rows.jsonl")
    for path in (first, second):
        (path / "paid-started.json").write_text(json.dumps({"run_id": path.name, "commit": "a" * 40}))
    stored = {"rows": [], "receipts": {}}
    def record(rows, receipts, *args):
        stored.update(rows=rows, receipts=receipts)
    monkeypatch.setattr(ci, "commit_results", record)
    monkeypatch.setattr(ci, "result_record", lambda rows=(), own_receipts=None: (
        ci.fold_rows(stored["rows"], rows), {**stored["receipts"], **(own_receipts or {})}))
    uploads = []
    def upload(output, repo, run_id, commit, **kwargs):
        assert sorted(stored["receipts"]) == ["12-10", "12-2"]
        assert [(r["epoch"], r["status"]) for r in stored["rows"]] == [(1, "passed"), (2, "passed")]
        uploads.append(run_id)
        if run_id == "12-2":
            raise RuntimeError("Old artifact upload failed")
        return {"rows_file": str(output / "rows.jsonl")}
    monkeypatch.setattr(ci, "publish_logs", upload)
    assert ci.publish_artifacts(argparse.Namespace(output=tmp_path, repo="owner/repo", publish=True)) == 1
    assert uploads == ["12-2", "12-10"]
    assert sorted(stored["receipts"]) == ["12-10", "12-2"]


def test_retry_opens_pr_after_successful_push(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "offline-unused")
    ci.command("git", "init", "-b", "main", capture_output=True)
    ci.command("git", "config", "user.name", "Test")
    ci.command("git", "config", "user.email", "test@example.org")
    ci.command("git", "commit", "--allow-empty", "-m", "Initial", capture_output=True)
    ci.command("git", "update-ref", "refs/remotes/origin/main", "HEAD")
    command, pushes, prs = ci.command, [], []
    def remote(*args, **kwargs):
        if args[:2] == ("git", "push"):
            pushes.append(args[3])
            return subprocess.CompletedProcess(args, 0)
        if args[:3] == ("gh", "pr", "create"):
            prs.append(args)
            if len(prs) == 1:
                raise subprocess.CalledProcessError(1, "gh pr create")
            return subprocess.CompletedProcess(args, 0)
        if args[0] == "gh":
            return subprocess.CompletedProcess(args, 0, stdout="[]")
        return command(*args, **kwargs)
    monkeypatch.setattr(ci, "command", remote)
    row = {"eval_id": "test", "epoch": 1, "status": "error", "attempt": 1}
    with pytest.raises(subprocess.CalledProcessError):
        ci.commit_results([row], {"12-1": {"commit": "a" * 40}}, "owner/repo", True)
    ci.commit_results(*ci.result_record(), "owner/repo", True)
    assert len(pushes) == 1
    assert len(prs) == 2
    assert ci.result_record() == ([row], {"12-1": {"commit": "a" * 40}})


def test_missing_log_artifact_blocks_payment(monkeypatch):
    monkeypatch.setattr(ci, "result_record", lambda: ([], {}))
    def api(*args, **kwargs):
        assert args[-1] == "repos/owner/repo/actions/artifacts?per_page=100&page=1"
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"artifacts": [
            {"name": "paid-12-1", "expired": False}]}))
    monkeypatch.setattr(ci, "command", api)
    with pytest.raises(ValueError, match="unrecorded paid attempts.*12-1"):
        ci.require_recorded_runs("owner/repo")


def test_plan_writes_paid_intent_without_a_provider(tmp_path, monkeypatch):
    config = load_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    monkeypatch.setattr("ethevals.actors.model_actor", lambda *a: pytest.fail("Provider constructed"))
    monkeypatch.setenv("GITHUB_RUN_ID", "12")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "step-output"))
    args = argparse.Namespace(output=tmp_path / "marker", rows=tmp_path / "rows.jsonl", restore_results=False,
                              models=["opus"], modes=["vanilla"], epochs=1, wall_seconds=16200, budget=10)
    assert ci.plan_paid(args, [evaluation], config) == 0
    source = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert json.loads((args.output / "paid-started.json").read_text()) == {"run_id": "12-2", "commit": source}
    assert (tmp_path / "step-output").read_text() == "ready=true\n"
    report = json.loads((args.output / "plan.json").read_text())
    assert (report["missing_epochs"], report["worst_case_usd"]) == (1, 10)


@pytest.mark.parametrize("identity", ["12", "12-two", "0-1", "12-0"])
def test_accept_loss_rejects_mistyped_identity(identity):
    result = cli("scripts/ci.py", "accept-loss", "--repo", "owner/repo", "--run-id", identity, "--reason", "Local proof")
    assert result.returncode == 2
    assert "RUN-ATTEMPT with positive integers" in result.stderr
