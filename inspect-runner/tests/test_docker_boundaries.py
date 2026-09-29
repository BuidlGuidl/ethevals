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
from test_docker import ROOT, containers

pytestmark = pytest.mark.docker


@pytest.mark.parametrize("local_oom,cli_code", [(True, 137), (False, 137), (True, 1)])
def test_agent_container_death_through_exported_rows(tmp_path, monkeypatch, local_oom, cli_code):
    from ethevals import agents
    from inspect_ai.util import sandbox
    from ethevals.sandboxes import runner_exec
    from ethevals.actors import player
    config = load_config()
    config.models["opus"].model = "mockllm/model"
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
    assert (row["status"], row["passed"]) == (("failed", False) if local_oom and cli_code == 137 else ("error", None)), row
    assert isinstance(row["agent_memory_peak_bytes"], int)
    assert row["agent_memory_peak_bytes"] > 0
    if local_oom:
        assert row["agent_memory_peak_bytes"] >= 128 * 1024 * 1024
    if local_oom and cli_code == 137:
        assert {c["reason"] for c in row["checks"].values()} == {"Agent exceeded its container memory limit."}
    else:
        assert f"Error executing claude code agent {cli_code}" in row["error_reason"]


def test_killed_check_wrapper_after_setup_exports_error(tmp_path):
    from inspect_ai.solver import solver
    from inspect_ai.util import sandbox
    config = load_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    compose = prepare_compose(evaluation, tmp_path)
    evaluation = prepare_eval(evaluation, tmp_path, compose)
    files = {**evaluation.files, "scorer/check.py": b'#!/usr/bin/env python3\nimport os, signal\n'
             b'print(\'{"balance":{"passed":true,"reason":"Balance matches."}}\', flush=True)\n'
             b'os.kill(os.getppid(), signal.SIGKILL)\n'}
    evaluation = replace(evaluation, files=files, hash=content_hash(files))
    compose = prepare_compose(evaluation, tmp_path)
    task = build_task(evaluation, config, check_player(evaluation, "empty"), check_grader(), "internet", 1, compose)

    @solver
    def setup_succeeded():
        async def solve(state, generate):
            assert await sandbox("chain").read_file("/eval/script.status") == "0"
            return state
        return solve

    task.solver = setup_succeeded()
    row = results_rows(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0])[0]
    assert (row["status"], row["passed"]) == ("error", None), row
    assert "check.py wrapper exited 137 without a script status" in row["error_reason"]


def test_scoring_deadline_kills_a_process_that_ignores_term(tmp_path):
    import anyio
    from ethevals.sandboxes import scoring_exec
    from ethevals.scoring_base import SubmissionFailed
    with containers(tmp_path) as boxes:
        async def proof():
            with pytest.raises(SubmissionFailed, match="Submission exceeded the scoring time limit"):
                await scoring_exec(boxes["scorer"], ["/bin/sh", "-c", "trap '' TERM; while :; do sleep 1; done"], timeout=.1)
        anyio.run(proof)


@pytest.mark.parametrize("kind", ["build", "act", "host_kill"])
def test_oom_during_grading_fails_fixed_checks(tmp_path, monkeypatch, kind):
    import subprocess
    import threading
    import time
    killed = []
    watcher = None
    config = load_config()
    folder = "transactions/send-six-decimal-token" if kind == "act" else "building/erc20-points-token"
    evaluation = load_eval(ROOT / "evals" / folder, config)
    compose = prepare_compose(evaluation, tmp_path)
    evaluation = prepare_eval(evaluation, tmp_path, compose)
    document = yaml.safe_load(compose.read_bytes())
    document["services"]["chain" if kind == "act" else "scorer"]["mem_limit"] = "128m"
    files = dict(evaluation.files)
    if kind == "act":
        files["scorer/check.py"] = b"#!/usr/bin/env python3\nallocation = bytearray(512 * 1024 * 1024)\n"
    evaluation = replace(evaluation, files=files, hash=content_hash(files))
    compose = prepare_compose(evaluation, tmp_path)
    compose.write_text(yaml.safe_dump(document))
    if kind != "act":
        from ethevals.scorers import prepare_forge as original
        from ethevals.sandboxes import runner_exec

        async def prepare(box, *args):
            nonlocal watcher
            await original(box, *args)
            script = """
compiler=$(find /home/agent/.svm -name 'solc-*' -type f | head -1)
cp "$compiler" /tmp/real-solc
cat > "$compiler" <<'SOLC'
#!/bin/sh
if [ "$1" = --version ]; then exec /tmp/real-solc "$@"; fi
exec /usr/bin/perl -e '$allocation = "x" x (512 * 1024 * 1024); sleep 1'
SOLC
chmod +x "$compiler"
"""
            if kind == "host_kill":
                script = script.replace('exec /usr/bin/perl -e \'$allocation = "x" x (512 * 1024 * 1024); sleep 1\'',
                                        'echo $$ > /tmp/compiler.pid\nexec /bin/sleep 90')
            result = await runner_exec(box, ["/bin/bash", "-c", script], user="root")
            assert result.success, result.stderr
            if kind == "host_kill":
                def kill_from_host():
                    for _ in range(100):
                        ids = subprocess.run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.service=scorer"],
                                             capture_output=True, text=True, check=True).stdout.split()
                        for container in ids:
                            result = subprocess.run(["docker", "exec", "-u", "root", container, "sh", "-c",
                                'test -f /tmp/compiler.pid && kill -9 "$(cat /tmp/compiler.pid)"'], capture_output=True)
                            if result.returncode == 0:
                                killed.append(container)
                                return
                        time.sleep(0.1)
                watcher = threading.Thread(target=kill_from_host)
                watcher.start()
        monkeypatch.setattr("ethevals.scorers.prepare_forge", prepare)
    task = build_task(evaluation, config, check_player(evaluation, "reference"), check_grader(), "internet", 1, compose)
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none", retry_on_error=0)[0]
    row = results_rows(log)[0]
    if kind == "host_kill":
        watcher.join(timeout=20)
        assert len(killed) == 1
        assert (row["status"], row["passed"]) == ("error", None), row
        assert "Forge exited 1" in row["error_reason"]
        return
    assert (row["status"], row["passed"]) == ("failed", False), row
    assert len(row["checks"]) == (2 if kind == "act" else 8)
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
    monkeypatch.setattr(preparation, "IMAGES", images)
    monkeypatch.setattr(sandboxes, "IMAGES", images)
    folder = tmp_path / "evals/building/custom"
    shutil.copytree(ROOT / "evals/building/erc20-points-token", folder)
    (folder / "compose.yaml").write_text("services:\n  extra:\n    image: " + tag + "\n    mem_limit: 64m\n")
    config = load_config()
    evaluation = load_eval(folder, config)
    for output, fresh in [(tmp_path / "pr", True), (tmp_path / "after-merge", False)]:
        success, rows = run([evaluation], config, output, answer="reference", epochs=1, fresh=fresh)
        assert (success, rows[0]["status"]) == (True, "passed")
        composed = yaml.safe_load((output / "inputs" / evaluation.hash / "compose.yaml").read_bytes())
        assert composed["services"]["scorer"]["image"] == tag
        assert all("build" not in service for service in composed["services"].values())
    subprocess.run(["docker", "image", "rm", tag], check=True, capture_output=True)
