"""Real Docker and Forge failures classified through Inspect rows."""
import json
from dataclasses import replace

import pytest
import yaml
from inspect_ai import eval

from ethevals.checks import check_grader, check_player
from ethevals.config import load_config
from ethevals.files import content_hash
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose, prepare_eval
from ethevals.rows import results_rows
from ethevals.runner import build_task, run
from ethevals.sandboxes import scoring_exec
from test_docker import ROOT, containers

pytestmark = pytest.mark.docker


@pytest.mark.parametrize("kind", ["build", "act"])
def test_oom_during_grading_fails_fixed_checks(tmp_path, monkeypatch, kind):
    config = load_config()
    folder = "building/erc20-points-token" if kind == "build" else "transactions/send-six-decimal-token"
    evaluation = load_eval(ROOT / "evals" / folder, config)
    compose = prepare_compose(evaluation, tmp_path)
    evaluation = prepare_eval(evaluation, tmp_path, compose)
    document = yaml.safe_load(compose.read_bytes())
    document["services"]["scorer" if kind == "build" else "chain"]["mem_limit"] = "128m"
    files = {**evaluation.files, "compose.yaml": yaml.safe_dump(document).encode()}
    if kind == "act":
        files["scorer/check.py"] = b"allocation = bytearray(512 * 1024 * 1024)\n"
    evaluation = replace(evaluation, files=files, hash=content_hash(files))
    compose = prepare_compose(evaluation, tmp_path)
    if kind == "build":
        async def oom_forge(box, *args):
            return await scoring_exec(box, ["/usr/bin/perl", "-e", '$allocation = "x" x (512 * 1024 * 1024); sleep 1'], timeout=20)
        monkeypatch.setattr("ethevals.scorers.forge", oom_forge)
    task = build_task(evaluation, config, check_player(evaluation, "reference"), check_grader(), "internet", 1, compose)
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none", retry_on_error=0)[0]
    row = results_rows(log)[0]
    assert (row["status"], row["passed"]) == ("failed", False), row
    assert len(row["checks"]) == (8 if kind == "build" else 2)
    assert {check["reason"] for check in row["checks"].values()} == {"Submission exceeded the scorer memory limit."}


def test_non_utf8_source_matches_real_forge_and_fails_checks(tmp_path):
    import anyio
    from ethevals.scorers import forge, prepare_forge
    config = load_config()
    original = load_eval(ROOT / "evals/building/erc20-points-token", config)
    source = b"pragma solidity =0.8.30; //\xff\ncontract BuilderPoints {}"
    with containers(tmp_path / "raw") as boxes:
        async def capture():
            box = boxes["scorer"]
            await prepare_forge(box, {"src/BuilderPoints.sol": b"pragma solidity =0.8.30; contract BuilderPoints {}"}, original.files)
            await box.write_file("/workspace/src/BuilderPoints.sol", source)
            return await forge(box)
        result = anyio.run(capture)
        assert result.returncode == 1
        assert "stream did not contain valid UTF-8" in result.stderr
        (tmp_path / "forge-invalid-utf8.json").write_text(json.dumps(result.model_dump() if hasattr(result, "model_dump") else vars(result)))
    files = {**original.files, "workspace/src/BuilderPoints.sol": source}
    evaluation = replace(original, files=files, hash=content_hash(files))
    success, rows = run([evaluation], config, tmp_path / "scored", answer="empty", epochs=1)
    assert success
    assert (rows[0]["status"], rows[0]["passed"]) == ("failed", False)
    assert {check["reason"] for check in rows[0]["checks"].values()} == {"Solidity source is not valid UTF-8: src/BuilderPoints.sol"}


def test_custom_compose_prepares_stock_images_for_check_and_run(tmp_path):
    import shutil
    from ethevals.sandboxes import IMAGES
    folder = tmp_path / "evals/building/custom"
    shutil.copytree(ROOT / "evals/building/erc20-points-token", folder)
    document = yaml.safe_load((IMAGES / "stock.compose.yaml").read_bytes())
    document["services"]["default"].pop("build")
    (folder / "compose.yaml").write_text(yaml.safe_dump(document))
    config = load_config()
    evaluation = load_eval(folder, config)
    for output, fresh in [(tmp_path / "pr", True), (tmp_path / "after-merge", False)]:
        success, rows = run([evaluation], config, output, answer="reference", epochs=1, fresh=fresh)
        assert (success, rows[0]["status"]) == (True, "passed")
        composed = yaml.safe_load((output / "inputs" / evaluation.hash / "compose.yaml").read_bytes())
        assert composed["services"]["scorer"]["image"] == "ethevals-solidity:inputs-f7690ccd7debdf27"
        assert all("build" not in service for service in composed["services"].values())
