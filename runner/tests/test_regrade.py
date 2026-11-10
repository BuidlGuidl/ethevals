import asyncio
import json
from pathlib import Path
import shutil

import litellm
import pytest

from ethevals.checks import read_reward
from ethevals.job_config import load_job
from ethevals.jobs import budget_check, plan, run
from ethevals.trial_rows import results_row, fold_rows
from support import recorded_trial
from test_jobs import job_config, task_folder
from test_task_judges import add_judge


def saved_trial(tmp_path):
    task = task_folder(tmp_path)
    config = load_job(job_config(tmp_path, "free"))
    item, = plan([task], config, [], n_attempts=1)["missing"]
    folder = tmp_path / "saved"
    recorded_trial(folder, task)
    row = results_row(folder, item)
    return task, config, row


def test_changed_concepts_checks_plan_regrades_and_missing_work_plans_a_rerun(tmp_path):
    task, config, row = saved_trial(tmp_path)
    (task / "tests/test.sh").write_text("Changed checks.\n")
    report = plan([task], config, [row], n_attempts=1, saved_work=tmp_path / "cache")
    assert (report["missing_trials"], report["regrade_trials"], report["worst_case_usd"]) == (0, 1, 0)
    regrade, = report["regrades"]
    assert (regrade["kind"], regrade["judge_required"], regrade["checks_generation"]) == ("concepts", False, 1)
    assert Path(regrade["saved_work"]["trajectory"]).read_bytes() == Path(row["trajectory_file"]).read_bytes()
    missing = {**row, "trajectory_file": None, "trajectory_url": None}
    report = plan([task], config, [missing], n_attempts=1, saved_work=tmp_path / "absent")
    rerun, = report["missing"]
    assert (report["regrade_trials"], rerun["trial"], rerun["retry"], rerun["checks_generation"]) == (0, 1, 0, 1)
    assert "saved trajectory is unavailable" in rerun["rerun_reason"]


def test_changed_browser_or_chain_checks_plan_fresh_trials(tmp_path):
    task = task_folder(tmp_path)
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace('pillar = "concepts"', 'pillar = "build"'))
    destination = tmp_path / "tasks/build/question"
    destination.parent.mkdir()
    task.rename(destination)
    config = load_job(job_config(tmp_path, "api_key"))
    old, = plan([destination], config, [], n_attempts=1)["missing"]
    (destination / "tests/browser.mjs").write_text("Changed browser checks.\n")
    report = plan([destination], config, [{**old, "status": "passed"}], n_attempts=1)
    rerun, = report["missing"]
    assert (report["regrade_trials"], rerun["retry"], rerun["worst_case_usd"], rerun["checks_generation"]) == (0, 0, 6, 1)
    assert rerun["rerun_reason"] == "The changed checks need a live browser or chain."


def test_criteria_only_regrade_reserves_the_judge_and_never_the_agent(tmp_path):
    task = task_folder(tmp_path)
    add_judge(task)
    config = load_job(job_config(tmp_path, "api_key"))
    old, = plan([task], config, [], n_attempts=1)["missing"]
    folder = tmp_path / "saved"
    recorded_trial(folder, task)
    details = {"reward": {"kind": "llm", "score": 1, "criteria": [], "judge": {
        "files": None, "atif_trajectory": "/logs/agent/trajectory.json"}}}
    (folder / "verifier/reward-details.json").write_text(json.dumps(details))
    row = {**old, "status": "passed", "trajectory_file": str(folder / "agent/trajectory.json"),
           "verifier_files": str(folder / "verifier")}
    judge = task / "tests/judge.toml"
    judge.write_text(judge.read_text().replace("explain the unit?", "explain the unit correctly?"))
    report = budget_check(plan([task], config, [row], n_attempts=1, saved_work=tmp_path / "cache"), 5)
    regrade, = report["regrades"]
    assert (report["missing_trials"], report["worst_case_usd"], report["within_budget"],
            regrade["kind"], regrade["judge_required"]) == (0, 6, False, "judge", True)
    with pytest.raises(ValueError, match="Budget exceeded"):
        asyncio.run(run(report, config, tmp_path / "out", [row]))
    assert not (tmp_path / "out/jobs").exists()


def test_rewardkit_reuses_a_judge_and_asks_again_only_for_changed_criteria_or_input(tmp_path, monkeypatch):
    from rewardkit.runner import run as rewardkit_run
    from ethevals.regrade_checks import replay
    from ethevals.task_hashes import digest

    source = tmp_path / "source"
    (source / "agent").mkdir(parents=True)
    trajectory = source / "agent/trajectory.json"
    trajectory.write_text(json.dumps({"steps": [{"source": "agent", "message": "metre"}]}))
    current_trajectory = tmp_path / "current-trajectory.json"
    shutil.copyfile(trajectory, current_trajectory)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "answer.py").write_text('from rewardkit import criterion\n@criterion\ndef unit(workspace):\n'
                                     '    return {"score": False, "reasoning": "Old check."}\n')
    (tests / "reward.toml").write_text('[[reward]]\nname = "reward"\naggregation = "all-pass"\n')
    judge = tests / "judge.toml"
    judge.write_text('[judge]\njudge = "openai/gpt-5"\nguard = "flag"\n'
                     f'atif-trajectory = "{current_trajectory}"\n[scoring]\naggregation = "all-pass"\n'
                     '[[criterion]]\nname = "explained"\ntype = "binary"\ndescription = "Was the unit explained?"\n')
    calls = []

    async def fake_judge(**kwargs):
        calls.append(kwargs)
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": json.dumps({
            "explained": {"score": "yes", "reasoning": "The reply names metre."},
            "guard": {"score": "no", "reasoning": "No judge instructions."}})}}])
    monkeypatch.setattr(litellm, "acompletion", fake_judge)
    rewardkit_run(tests, workspace=tmp_path, output=source / "saved-verifier/reward.json")
    assert read_reward(source / "saved-verifier")[0] == {"reward": 0.0}
    inputs = {"tests/judge.toml": digest(judge.read_text()), "@judge": {"model": "openai/gpt-5", "effort": None}}
    item = {"source_row": {"checks_inputs": inputs}, "checks_inputs": dict(inputs), "judge_required": False}
    item_file = tmp_path / "item.json"
    monkeypatch.setenv("ETHEVALS_REGRADE_ITEM", str(item_file))
    monkeypatch.setenv("ETHEVALS_REGRADE_SOURCE", str(source))
    (tests / "answer.py").write_text((tests / "answer.py").read_text().replace('False', 'True').replace("Old check.", "Fixed check."))
    item_file.write_text(json.dumps(item))
    replay(tests, workspace=tmp_path, output=tmp_path / "new/reward.json")
    assert read_reward(tmp_path / "new") == ({"reward": 1.0}, {
        "unit": {"passed": True, "reason": "Fixed check."},
        "explained": {"passed": True, "reason": "The reply names metre."}})
    assert len(calls) == 1
    judge.write_text(judge.read_text().replace("unit explained?", "unit fully explained?"))
    item["checks_inputs"]["tests/judge.toml"] = digest(judge.read_text())
    item["judge_required"] = True
    item_file.write_text(json.dumps(item))
    replay(tests, workspace=tmp_path, output=tmp_path / "changed/reward.json")
    assert (len(calls), read_reward(tmp_path / "changed")[0]) == (2, {"reward": 1.0})
    item["source_row"]["checks_inputs"] = dict(item["checks_inputs"])
    current_trajectory.write_text(json.dumps({"steps": [{"source": "agent", "message": "metres"}]}))
    item["judge_required"] = False
    item_file.write_text(json.dumps(item))
    with pytest.raises(ValueError, match="without a judge reserve"):
        replay(tests, workspace=tmp_path, output=tmp_path / "unreserved/reward.json")
    assert len(calls) == 2
    item["judge_required"] = True
    item_file.write_text(json.dumps(item))
    replay(tests, workspace=tmp_path, output=tmp_path / "new-input/reward.json")
    assert (len(calls), read_reward(tmp_path / "new-input")[0]) == (3, {"reward": 1.0})


def test_a_regrade_replaces_an_old_retry_without_changing_the_original_model_cost(tmp_path):
    _, _, row = saved_trial(tmp_path)
    old = {**row, "retry": 1, "status": "failed"}
    new = {**old, "checks_generation": 1, "retry": 0, "status": "passed", "checks_hash": "new"}
    assert fold_rows([new], [old]) == [new]
    assert fold_rows([old], [new]) == [new]


@pytest.mark.docker
def test_concepts_regrade_runs_real_tests_and_publishes_one_verifier_archive(tmp_path, monkeypatch):
    from harbor.job import Job
    from ethevals.publish import publish_logs
    from ethevals.secret_check import stage_artifact
    from ethevals.trial_rows import recover_rows

    task = tmp_path / "concepts/question"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/concepts/question", task)
    config = load_job(job_config(tmp_path, "free"))
    item, = plan([task], config, [], n_attempts=1)["missing"]
    source = tmp_path / "source"
    recorded_trial(source, task)
    old = results_row(source, item, trajectory_url="https://example.org/original.json")
    old["model_cost_usd"] = 4.25
    (task / "tests/answer.py").write_text((task / "tests/answer.py").read_text().replace('== "metre"', '== "centimetre"'))
    report = budget_check(plan([task], config, [old], n_attempts=1, saved_work=tmp_path / "cache"), 0)

    async def no_agent(*args):
        raise AssertionError("A regrade cannot run an agent.")
    monkeypatch.setattr(Job, "run", no_agent)
    output = tmp_path / "out"
    assert asyncio.run(run(report, config, output, [old])) is True
    row, = recover_rows(output)
    assert (row["status"], row["model_cost_usd"], row["trajectory_url"], row["checks_hash"], row["checks"]) == (
        "failed", 4.25, "https://example.org/original.json", report["regrades"][0]["checks_hash"],
        {"unit": {"passed": False, "reason": "The final reply is absent or differs."}})
    release = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])
    assert [asset["name"].split("-")[0] for asset in release["assets"]] == ["verifier"]
    assert release["rows"][0]["trajectory_url"] == old["trajectory_url"]
    stage_artifact(output, tmp_path / "artifact")
    moved, = recover_rows(tmp_path / "artifact")
    assert (moved["checks"], moved["model_cost_usd"], moved["trajectory_url"]) == (
        row["checks"], 4.25, old["trajectory_url"])
    import argparse
    from test_ci import ci
    downloads = tmp_path / "downloads"
    shutil.copytree(tmp_path / "artifact", downloads / "trial-run-12-1-regrade-0")
    assert ci.publish_artifacts(argparse.Namespace(
        output=downloads, repo="owner/repo", run_id="12", commit="a" * 40, publish=False)) == 0
    published = [json.loads(line) for line in (downloads / "combined/rows.jsonl").read_text().splitlines()]
    assert [(r["status"], r["model_cost_usd"]) for r in published if r["task_id"] == "concepts/question"] == [("failed", 4.25)]
    assert len(json.loads((downloads / "combined/release.json").read_text())["assets"]) == 1


def test_ci_batches_640_concepts_regrades_in_one_job_without_trials(tmp_path):
    from ethevals.trial_rows import write_rows
    from support import cli
    task, config, row = saved_trial(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json())
    rows = tmp_path / "rows.jsonl"
    write_rows(rows, [{**row, "trial": number} for number in range(1, 641)])
    (task / "tests/test.sh").write_text("Changed checks.\n")
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    completed = cli(Path(__file__).resolve().parents[2] / "scripts/ci.py", "plan-trials", "--config", config_path,
                    "--tasks", task, "--n-attempts", 640, "--rows", rows, "--budget", 1,
                    "--output", output, "--github-output", github_output)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((output / "plan.json").read_text())
    assert (report["missing_trials"], report["regrade_trials"], report["worst_case_usd"]) == (0, 640, 0)
    batch, = json.loads((output / "regrades.json").read_text())
    assert (len(batch["regrades"]), batch["missing_trials"], batch["worst_case_usd"]) == (640, 0, 0)
    emitted = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
    assert (emitted["scheduled_trials"], emitted["scheduled_regrades"], json.loads(emitted["regrade_matrix"])) == (
        "0", "1", {"include": [{"index": 0, "task_id": "concepts/question", "judge": False}]})
