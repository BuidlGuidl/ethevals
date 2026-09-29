from pathlib import Path
import json

from ethevals.actors import select_actors
from ethevals.loader import load_eval
from ethevals.planning import budget_check, plan
from ethevals.rows import epoch_identity, write_rows
import pytest

from support import catalog_quiz, cli, eval_cli, fixture_config, run, small_config


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("command", ["plan", "run"])
@pytest.mark.parametrize("selection,message", [
    (["--modes", "vanilla", "--agents", "claude-code-opus-5.5"], "--agents requires an internet or skills mode"),
    (["--modes", "internet", "skills", "--models", "opus-5.5"], "--models requires the vanilla mode"),
])
def test_selector_requires_a_matching_mode(command, selection, message):
    result = eval_cli(command, "--evals", ROOT / "evals/concepts/agent-registries", *selection)
    assert result.returncode == 2
    assert message in result.stderr


@pytest.mark.parametrize("selectors,expected", [
    ([], [("vanilla", 4), ("internet", 4), ("skills", 4)]),
    (["--models", "opus-5.5"], [("vanilla", 1)]),
    (["--agents", "claude-code-opus-5.5"], [("internet", 1), ("skills", 1)]),
    (["--models", "opus-5.5", "--agents", "claude-code-opus-5.5"], [("vanilla", 1), ("internet", 1), ("skills", 1)]),
])
def test_plan_derives_modes_from_selectors(tmp_path, selectors, expected):
    from collections import Counter
    result = eval_cli("plan", "--evals", ROOT / "evals/concepts/agent-registries",
                      "--epochs", 1, "--output", tmp_path, *selectors)
    assert result.returncode == 0, result.stderr
    assert list(Counter(row["mode"] for row in json.loads(result.stdout)["missing"]).items()) == expected


def test_declared_modes_skip_ineligible_evals(folder, tmp_path):
    path = folder / "eval.yaml"
    path.write_text(path.read_text().replace("[vanilla, internet]", "[internet]"))
    config = fixture_config()
    vanilla = load_eval(ROOT / "inspect-runner/tests/fixtures/concepts/wei-per-ether", config)
    internet = load_eval(folder, config)
    success, rows = run([internet, vanilla], config, tmp_path / "results", answer="reference", epochs=1,
                        modes=["vanilla"])
    assert success is True
    assert [(row["eval_id"], row["mode"], row["status"]) for row in rows] == [
        ("concepts/wei-per-ether", "vanilla", "passed")]
    with pytest.raises(ValueError, match="No evals declare a selected mode"):
        run([internet], config, tmp_path / "none", modes=["skills"], answer="reference")


def test_paid_run_needs_budget_before_constructing_provider(tmp_path, monkeypatch):
    config, evaluation = catalog_quiz()
    monkeypatch.setattr("ethevals.actors.model_actor", lambda *args: pytest.fail("Provider constructed"))
    with pytest.raises(ValueError, match="requires --budget"):
        run([evaluation], config, tmp_path, agents=["claude-code-opus-5.5"], epochs=1)
    with pytest.raises(ValueError, match="Budget exceeded"):
        run([evaluation], config, tmp_path, agents=["claude-code-opus-5.5"], epochs=1, budget=0)


@pytest.mark.parametrize("effort", [None, "high"])
def test_admitted_config_keys_keep_different_efforts_on_the_same_model(tmp_path, effort):
    config, evaluation = catalog_quiz()
    first = config.models["opus-5.5"].model_copy(update={"model": "mockllm/shared", "effort": effort})
    config.models = {"first": first, "low": first.model_copy(update={"effort": "low"})}
    config.grader.model = "mockllm/grader"
    success, rows = run([evaluation], config, tmp_path, models=["first", "low"], modes=["vanilla"], epochs=1, budget=20)
    assert success
    assert [(row["effort"], row["status"], row["attempt"]) for row in rows] == [
        (effort, "failed", 1), ("low", "failed", 1)]


@pytest.mark.parametrize("mode", ["vanilla", "internet", "skills"])
def test_planned_identity_matches_every_configured_provider(mode):
    config, evaluation = catalog_quiz()
    for key, settings in (config.models if mode == "vanilla" else config.agents).items():
        selection = {"models" if mode == "vanilla" else "agents": [key], "modes": [mode]}
        planned, _ = select_actors(config, **selection, planning=True)
        actual, _ = select_actors(config, **selection)
        harness = settings.harness if mode != "vanilla" else None
        model = config.models[settings.model] if harness else settings
        expected = (evaluation.id, evaluation.hash, harness,
                    model.model, model.effort, mode, 1)
        for actors_for in (planned, actual):
            actor = actors_for(evaluation)[0][1]
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
    evaluation = load_eval(ROOT / "inspect-runner/tests/fixtures/building/erc20-points-token", config)
    agents_for, _ = select_actors(config, agents=["claude-code-opus-5.5"], modes=["internet"], planning=True)
    report = budget_check(plan([evaluation], config, agents_for, [], epochs=1).report, 27.6)
    assert report["missing"][0]["per_attempt_usd"] == 13.75835
    assert (report["worst_case_usd"], report["within_budget"]) == (27.5167, True)


@pytest.mark.parametrize("present,missing", [
    ([], "ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY"),
    (["OPENAI_API_KEY"], "ANTHROPIC_API_KEY, OPENROUTER_API_KEY"),
    (["OPENAI_API_KEY", "OPENROUTER_API_KEY"], "ANTHROPIC_API_KEY"),
])
def test_paid_run_names_only_missing_provider_keys(tmp_path, monkeypatch, present, missing):
    config, evaluation = catalog_quiz()
    for key, provider in [("gpt-5.5", "openai"), ("kimi-k3", "openrouter")]:
        model = config.models[key]
        config.prices[f"{provider}/test"] = config.prices[model.model]
        model.model = f"{provider}/test"
    config.grader.model = "anthropic/grader"
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    for key in present:
        monkeypatch.setenv(key, "inert-test-key")
    monkeypatch.setattr("ethevals.actors.model_actor", lambda *args: pytest.fail("Provider constructed"))
    with pytest.raises(ValueError) as error:
        run([evaluation], config, tmp_path, models=["gpt-5.5", "kimi-k3"], epochs=1, budget=100)
    assert str(error.value) == f"Missing provider keys for paid epochs: {missing}"
