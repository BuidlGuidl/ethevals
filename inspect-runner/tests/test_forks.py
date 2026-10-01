from pathlib import Path
import shutil

import pytest
import yaml

from ethevals.checks import available_checks
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.runner import run
from support import eval_cli, fixture_config


ROOT = Path(__file__).resolve().parents[2]
VESTING = ROOT / "evals/transactions/vesting-claim"


@pytest.mark.parametrize("network,variable", [("mainnet", "MAINNET_RPC_URL"), ("base", "BASE_RPC_URL")])
def test_fork_compose_keeps_the_rpc_url_out_of_saved_files(tmp_path, monkeypatch, network, variable):
    folder = tmp_path / "transactions/fork"
    shutil.copytree(VESTING, folder)
    declaration = yaml.safe_load((folder / "eval.yaml").read_text())
    declaration["chain"]["fork"] = network
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    evaluation = load_eval(folder, fixture_config())
    assert evaluation.declaration.chain.model_dump() == {"fork": network, "block": 23819000}
    fake_url = "https://archive.example/secret-file-probe"
    monkeypatch.setenv(variable, fake_url)
    output = tmp_path / "output"
    path = prepare_compose(evaluation, output)
    document = yaml.safe_load(path.read_text())
    assert document["services"]["chain"]["environment"] == {
        "FORK_RPC_URL": "${" + variable + "}", "FORK_BLOCK_NUMBER": "23819000"}
    assert document["services"]["chain"]["mem_limit"] == "1g"
    for name in ("default", "scorer"):
        assert "environment" not in document["services"][name]
    saved = [file.read_bytes() for file in output.rglob("*") if file.is_file()]
    assert len(saved) == 1
    assert all(fake_url.encode() not in content for content in saved)
    fresh = load_eval(ROOT / "evals/transactions/send-six-decimal-token", fixture_config())
    fresh_document = yaml.safe_load(prepare_compose(fresh, output).read_text())
    assert fresh_document["services"]["chain"]["mem_limit"] == "256m"
    assert "environment" not in fresh_document["services"]["chain"]


@pytest.mark.parametrize("chain", [
    {"fork": "mainnet"}, {"fork": "arbitrum", "block": 1},
    {"fork": "base", "block": 0}, {"fork": "base", "block": -1},
    {"fork": "base", "block": True}, {"fork": "base", "block": "1"},
    {"fork": "base", "block": 1, "url": "https://example.com"},
])
def test_invalid_fork_declarations_fail_validation(folder, chain):
    declaration = {"motivation": "Read the chain.", "prompt": "Read the balance.",
                   "modes": ["internet"], "chain": chain}
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    with pytest.raises(ValueError, match="chain"):
        load_eval(folder, fixture_config())


def test_fork_check_validates_and_skips_without_its_rpc_variable(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MAINNET_RPC_URL", raising=False)
    output = tmp_path / "output"
    result = eval_cli("check", "--evals", VESTING, "--output", output)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "transactions/vesting-claim: validated; skipped reference and untouched passes because MAINNET_RPC_URL is unset.\n")
    assert not output.exists()
    evaluation = load_eval(VESTING, fixture_config())
    monkeypatch.setenv("MAINNET_RPC_URL", "https://archive.example/check-probe")
    assert available_checks([evaluation]) == [evaluation]
    assert capsys.readouterr().out == ""


def test_fork_run_fails_before_creating_output_without_its_rpc_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("MAINNET_RPC_URL", raising=False)
    config = fixture_config()
    evaluation = load_eval(VESTING, config)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="Missing fork RPC variables: MAINNET_RPC_URL"):
        run([evaluation], config, output, answer="reference", epochs=1)
    assert not output.exists()
