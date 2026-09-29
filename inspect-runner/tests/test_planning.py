from pathlib import Path
import json

from ethevals.actors import select_actors
from ethevals.loader import load_eval
from ethevals.planning import budget_check, plan
from ethevals.rows import epoch_identity, fold_rows, write_rows
import pytest

from support import catalog_quiz, cli, eval_cli, fixture_config, run, small_config


ROOT = Path(__file__).resolve().parents[2]


def test_declared_modes_skip_ineligible_evals(folder, tmp_path):
    path = folder / "eval.yaml"
    path.write_text(path.read_text().replace("[vanilla, internet]", "[internet]"))
    config = fixture_config()
    vanilla = load_eval(ROOT / "evals/concepts/wei-per-ether", config)
    internet = load_eval(folder, config)
    success, rows = run([internet, vanilla], config, tmp_path / "results", answer="reference", epochs=1,
                        modes=["vanilla"])
    assert success is True
    assert [(row["eval_id"], row["mode"], row["status"]) for row in rows] == [
        ("concepts/wei-per-ether", "vanilla", "passed")]
    result = eval_cli("check", "--evals", folder, vanilla.folder, "--modes", "vanilla",
                     "--epochs", 1, "--output", tmp_path / "check")
    assert result.returncode == 0, result.stdout + result.stderr
    path.write_text(path.read_text().replace("[internet]", "[internet, skills]"))
    assert load_eval(folder, config).declaration.modes == ["internet", "skills"]
    with pytest.raises(ValueError, match="No evals declare a selected mode"):
        run([internet], config, tmp_path / "none", modes=["skills"], answer="reference")


def test_selected_modes_cross_only_declared_modes(folder, tmp_path):
    config = fixture_config()
    evaluation = load_eval(folder, config)
    success, rows = run([evaluation], config, tmp_path / "results", answer="reference", epochs=1,
                        modes=["vanilla", "internet", "skills"])
    assert success is True
    assert [(row["mode"], row["status"]) for row in rows] == [("internet", "passed"), ("vanilla", "passed")]


def test_paid_run_needs_budget_before_constructing_provider(tmp_path, monkeypatch):
    config, evaluation = catalog_quiz()
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-test-key")
    monkeypatch.setattr("ethevals.actors.model_actor", lambda *args: pytest.fail("Provider constructed"))
    with pytest.raises(ValueError, match="requires --budget"):
        run([evaluation], config, tmp_path, agents=["opus"], epochs=1)
    with pytest.raises(ValueError, match="Budget exceeded"):
        run([evaluation], config, tmp_path, agents=["opus"], epochs=1, budget=0)


def test_admission_reaches_every_epoch():
    config = small_config()
    evals = [load_eval(ROOT / "evals/concepts" / name, config)
             for name in ("agent-registries", "wei-per-ether")]
    agents_for, _ = select_actors(config, modes=["vanilla"], planning=True)
    recorded = []
    while True:
        report = plan(evals, config, agents_for, recorded, wall_seconds=2600).report
        assert report["missing_epochs"] > 0
        recorded = fold_rows(recorded, [{**row, "status": "passed"} for row in report["missing"]])
        if not report["deferred_epochs"]:
            break
        assert len(recorded) < 6
    assert [(row["eval_id"], row["epoch"]) for row in recorded] == [
        ("concepts/agent-registries", 1), ("concepts/agent-registries", 2),
        ("concepts/agent-registries", 3), ("concepts/wei-per-ether", 1),
        ("concepts/wei-per-ether", 2), ("concepts/wei-per-ether", 3)]
    assert plan(evals, config, agents_for, recorded, wall_seconds=2600).report["missing_epochs"] == 0


def test_plan_rejects_one_epoch_larger_than_empty_window():
    config = small_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    agents_for, _ = select_actors(config, modes=["vanilla"], planning=True)
    with pytest.raises(ValueError, match="Config error: a single epoch.*concepts/agent-registries"):
        plan([evaluation], config, agents_for, [], wall_seconds=1900)


def test_run_executes_saved_plan(tmp_path):
    config = small_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    success, rows = run([evaluation], config, tmp_path, answer="reference", wall_seconds=2150)
    report = json.loads((tmp_path / "plan.json").read_text())
    assert success
    assert [(row["epoch"], row["status"]) for row in rows] == [(1, "passed"), (2, "passed")]
    assert [row["epoch"] for row in report["missing"]] == [1, 2]
    assert [row["epoch"] for row in report["deferred"]] == [3]


def test_run_prepares_only_initially_admitted_evals(tmp_path, monkeypatch):
    import ethevals.runner as runner
    config = small_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    deferred = load_eval(ROOT / "evals/concepts/wei-per-ether", config)
    original = runner.prepare_compose

    def prepare(evaluation, *args):
        if evaluation.id == deferred.id:
            raise RuntimeError("Deferred eval was prepared")
        return original(evaluation, *args)

    monkeypatch.setattr(runner, "prepare_compose", prepare)
    success, rows = run([evaluation, deferred], config, tmp_path, answer="reference", epochs=1, wall_seconds=2000)
    assert (success, [(row["eval_id"], row["status"]) for row in rows]) == (
        True, [("concepts/agent-registries", "passed")])


@pytest.mark.parametrize("folder, mode, seconds", [
    ("building/erc20-points-token", "internet", 3840),
    ("concepts/agent-registries", "vanilla", 3120),
])
def test_plan_includes_scoring_and_only_sandbox_container_time(folder, mode, seconds):
    config = small_config()
    config.time_limits = {"quiz": 1000, "build": 1000, "act": 1000}
    evaluation = load_eval(ROOT / "evals" / folder, config)
    agents_for, _ = select_actors(config, modes=[mode], planning=True)
    report = plan([evaluation], config, agents_for, [], epochs=1).report
    assert [(row["eval_id"], row["wall_seconds"]) for row in report["missing"]] == [(folder, seconds)]


def test_admitted_config_keys_keep_different_efforts_on_the_same_model(tmp_path, monkeypatch):
    config, evaluation = catalog_quiz()
    first = config.agents["opus"].model_copy(update={"model": "mockllm/shared", "harness": None})
    config.agents = {"high": first, "low": first.model_copy(update={"effort": "low"})}
    config.grader.model = "mockllm/grader"
    # Both providers are MockLLM. The gate key never reaches a provider request.
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-offline-gate-key")
    success, rows = run([evaluation], config, tmp_path, agents=["high", "low"], modes=["vanilla"], epochs=1, budget=20)
    assert success
    assert [(row["effort"], row["status"], row["attempt"]) for row in rows] == [
        ("high", "failed", 1), ("low", "failed", 1)]


@pytest.mark.parametrize("mode", ["vanilla", "internet", "skills"])
def test_planned_identity_matches_every_configured_provider(monkeypatch, mode):
    config, evaluation = catalog_quiz()
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-test-key")
    for key, settings in config.agents.items():
        planned, _ = select_actors(config, [key], [mode], planning=True)
        actual, _ = select_actors(config, [key], [mode])
        expected = (evaluation.id, evaluation.hash, settings.harness if mode != "vanilla" else None,
                    settings.model, settings.effort, mode, 1)
        for selection in (planned, actual):
            actor = selection(evaluation)[0][1]
            assert epoch_identity({"eval_id": evaluation.id, "eval_hash": evaluation.hash, "mode": mode,
                                   **actor.metadata}, 1) == expected


def test_budget_stops_before_preparation(tmp_path, monkeypatch):
    config = small_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    monkeypatch.setattr("ethevals.runner.prepare_compose", lambda *a: pytest.fail("Preparation ran"))
    with pytest.raises(ValueError, match="Budget exceeded"):
        run([evaluation], config, tmp_path, budget=1, epochs=1, modes=["vanilla"])
    report = json.loads((tmp_path / "plan.json").read_text())
    assert (report["worst_case_usd"], report["missing_epochs"], report["within_budget"]) == (4, 1, False)


def test_plan_is_key_free_and_reserves_remaining_attempts(tmp_path):
    from support import small_config
    config = small_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config.model_dump_json())
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    base = {"eval_id": quiz.id, "eval_hash": quiz.hash, "type": "quiz", "harness": None,
            "model": "mockllm/test", "effort": "high", "mode": "vanilla"}
    rows = [{**base, "epoch": 1, "status": "failed", "attempt": 1},
            {**base, "epoch": 2, "status": "error", "attempt": 1},
            {**base, "epoch": 3, "status": "error", "attempt": 2}]
    store = tmp_path / "rows.jsonl"
    write_rows(store, rows)
    result = cli("-m", "ethevals.cli", "plan", "--config", config_path, "--output", tmp_path,
                 "--rows", store, "--evals", quiz.folder, "--modes", "vanilla", "--budget", "1")
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert [(r["epoch"], r["attempt"], r["remaining_attempts"]) for r in report["missing"]] == [(2, 2, 1)]
    assert [(r["epoch"], r["attempt"]) for r in report["exhausted_errors"]] == [(3, 2)]
    assert (report["worst_case_usd"], report["within_budget"]) == (2, False)


def test_build_plan_reserves_capped_grader_requests():
    config = fixture_config()
    evaluation = load_eval(ROOT / "evals/building/erc20-points-token", config)
    agents_for, _ = select_actors(config, ["opus"], ["internet"], planning=True)
    report = budget_check(plan([evaluation], config, agents_for, [], epochs=1).report, 29.6)
    assert report["missing"][0]["per_attempt_usd"] == 14.75445
    assert (report["worst_case_usd"], report["within_budget"]) == (29.5089, True)
