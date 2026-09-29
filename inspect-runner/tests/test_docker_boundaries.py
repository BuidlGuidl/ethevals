"""Real Docker and Forge failures classified through Inspect rows."""
import json
from dataclasses import replace

import pytest
import yaml
from inspect_ai import eval

from ethevals.checks import check_grader
from support import load_config
from ethevals.files import content_hash
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.rows import results_rows
from ethevals.runner import build_task, run
from test_docker import ROOT, containers

pytestmark = pytest.mark.docker


@pytest.mark.parametrize("script,status,reason", [
    (b'print("x" * (11 * 1024 * 1024))', "failed", "malformed JSON"),
    (b'print("not JSON")', "failed", "malformed JSON"),
    (b'raise ValueError("bad amount")', "failed", "ValueError: bad amount"),
    (b'import os, signal; os.kill(os.getpid(), signal.SIGKILL)', "error", "exit code 137"),
])
def test_check_script_failures_through_task(tmp_path, script, status, reason):
    import shutil
    config = load_config()
    folder = tmp_path / "transactions/script"
    shutil.copytree(ROOT / "evals/transactions/send-six-decimal-token", folder)
    (folder / "scorer/check.py").write_bytes(script)
    evaluation = load_eval(folder, config)
    success, rows = run([evaluation], config, tmp_path / "results", answer="empty", epochs=1)
    row = rows[0]
    assert (success, row["status"]) == (status != "error", status)
    if status == "failed":
        assert set(row["checks"]) == {"script:check"}
        assert row["checks"]["script:check"]["passed"] is False
        assert reason in row["checks"]["script:check"]["reason"]
    else:
        assert reason in row["error_reason"]


@pytest.mark.parametrize("local_oom,cli_code", [(True, 137), (False, 137), (True, 1)])
def test_agent_container_death_through_exported_rows(tmp_path, monkeypatch, local_oom, cli_code):
    from ethevals import agents
    from inspect_ai.util import sandbox
    from ethevals.sandboxes import runner_exec
    from ethevals.actors import player
    config = load_config()
    config.agents["opus"].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    compose = prepare_compose(evaluation, tmp_path)
    document = yaml.safe_load(compose.read_bytes())
    document["services"]["default"]["mem_limit"] = "128m"
    compose.write_text(yaml.safe_dump(document))

    async def killed(state, generate):
        command = ["/usr/bin/perl", "-e", '$allocation = "x" x (512 * 1024 * 1024); sleep 1'] if local_oom else [
            "/bin/sh", "-c", "kill -9 $$"]
        result = await runner_exec(sandbox("default"), command)
        if not result.success:
            assert result.returncode == 137
            # The CLI can survive its child's OOM and fail later for another cause.
            if cli_code == 1:
                result = await runner_exec(sandbox("default"), ["/bin/sh", "-c", "exit 1"])
            raise RuntimeError(f"Error executing claude code agent {result.returncode}: CLI failure")
        raise AssertionError("The death proof survived")

    monkeypatch.setitem(agents.AGENTS, "claude_code", agents.Harness(lambda *a, **kw: killed, "proof"))
    task = build_task(evaluation, config, player(config, "opus", "internet"), check_grader(), "internet", 1, compose)
    row = results_rows(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0])[0]
    assert row["status"] == "error", row
    assert f"Error executing claude code agent {cli_code}" in row["error_reason"]


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
            return await forge(box, timeout=180)
        result = anyio.run(capture)
        assert result.returncode == 1
        assert "stream did not contain valid UTF-8" in result.stderr
        (tmp_path / "forge-invalid-utf8.json").write_text(json.dumps(result.model_dump() if hasattr(result, "model_dump") else vars(result)))
    files = {**original.files, "workspace/src/BuilderPoints.sol": source}
    evaluation = replace(original, files=files, hash=content_hash(files))
    success, rows = run([evaluation], config, tmp_path / "scored", answer="empty", epochs=1)
    assert success
    assert (rows[0]["status"], (None if rows[0]["status"] == "error" else rows[0]["status"] == "passed")) == ("failed", False)
    assert {check["reason"] for check in rows[0]["checks"].values()} == {"Solidity source is not valid UTF-8: src/BuilderPoints.sol"}


def test_custom_compose_prepares_stock_images_for_check_and_run(tmp_path, monkeypatch):
    import shutil
    import uuid
    import subprocess
    from ethevals.sandboxes import IMAGES
    from ethevals.images.tag import image_tag
    import ethevals.preparation as preparation
    import ethevals.sandboxes as sandboxes
    images = tmp_path / "images"
    shutil.copytree(IMAGES, images)
    dockerfile = images / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text() + "\nLABEL build-proof=" + uuid.uuid4().hex + "\n")
    tag = image_tag(images)
    for path in images.glob("*.compose.yaml"):
        data = yaml.safe_load(path.read_bytes())
        for name in ("default", "scorer"):
            data["services"][name]["image"] = tag
        path.write_text(yaml.safe_dump(data))
    monkeypatch.setattr(preparation, "IMAGES", images)
    monkeypatch.setattr(sandboxes, "IMAGES", images)
    folder = tmp_path / "evals/building/custom"
    shutil.copytree(ROOT / "evals/building/erc20-points-token", folder)
    document = yaml.safe_load((images / "stock.compose.yaml").read_bytes())
    document["services"]["default"].pop("build")
    (folder / "compose.yaml").write_text(yaml.safe_dump(document))
    config = load_config()
    evaluation = load_eval(folder, config)
    for output, fresh in [(tmp_path / "pr", True), (tmp_path / "after-merge", False)]:
        success, rows = run([evaluation], config, output, answer="reference", epochs=1, fresh=fresh)
        assert (success, rows[0]["status"]) == (True, "passed")
        composed = yaml.safe_load((output / "inputs" / evaluation.hash / "compose.yaml").read_bytes())
        assert composed["services"]["scorer"]["image"] == tag
        assert all("build" not in service for service in composed["services"].values())
    subprocess.run(["docker", "image", "rm", tag], check=True, capture_output=True)
