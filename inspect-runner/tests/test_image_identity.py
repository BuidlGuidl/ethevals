"""Image names identify build inputs; discovery also identifies grading inputs."""
import shutil
from pathlib import Path

import pytest
import yaml

from ethevals.config import load_config
from ethevals.images.tag import BUILD_INPUTS, image_inputs, image_tag
from ethevals.loader import load_eval
from ethevals.preparation import check_cache_path, prepare_compose
from ethevals.sandboxes import IMAGES

ROOT = Path(__file__).resolve().parents[2]


def test_runner_image_changes_leave_eval_hash_unchanged(tmp_path, monkeypatch):
    import ethevals.sandboxes as sandboxes
    from ethevals.sandboxes import merged_compose
    images = tmp_path / "images"
    shutil.copytree(IMAGES, images)
    monkeypatch.setattr(sandboxes, "IMAGES", images)
    folder = tmp_path / "building" / "extra"
    shutil.copytree(ROOT / "evals/building/erc20-points-token", folder)
    (folder / "compose.yaml").write_text("services:\n  database:\n    image: postgres:17\n    mem_limit: 512m\n")
    before = load_eval(folder, load_config())
    first = merged_compose(before)["services"]["default"]["image"]
    dockerfile = images / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text() + "\nLABEL test=changed\n")
    after = load_eval(folder, load_config())
    merged = merged_compose(after)["services"]
    assert after.hash == before.hash
    assert merged["default"]["image"] != first
    assert merged["database"] == {"image": "postgres:17", "mem_limit": "512m", "networks": ["private"]}


def test_rows_record_both_build_identities(tmp_path):
    from dataclasses import replace
    from inspect_ai import eval
    from ethevals.checks import check_grader, check_player
    from ethevals.rows import results_rows
    from ethevals.runner import build_task
    from ethevals.scorers import SCORERS
    from ethevals.scoring_base import checks_score
    from unittest.mock import patch

    config = load_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    evaluation = replace(evaluation, discovered_checks={"check_script": ("script:balance",)})
    task = build_task(evaluation, config, check_player(evaluation, "empty"), check_grader(), "internet", 1,
                      prepare_compose(evaluation, tmp_path))
    task.dataset[0].sandbox = task.dataset[0].files = None

    def build(*args):
        async def score(*args):
            return checks_score({"script:balance": {"passed": False, "reason": "No transfer."}})
        return score

    with patch.dict(SCORERS, {"check_script": replace(SCORERS["check_script"], build=build, capture=None)}):
        log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(log)[0]
    assert (row["status"], row["checks"]) == ("failed", {"script:balance": {"passed": False, "reason": "No transfer."}})
    assert row["images"] == {"default": image_tag(IMAGES), "scorer": image_tag(IMAGES), "chain": image_tag(IMAGES, "chain")}
    assert row["runner_inputs"] == image_inputs(IMAGES)
    assert row["chain_inputs"] == image_inputs(IMAGES, "chain")
    assert set(row["runner_inputs"]) == {"Dockerfile", "solc.json"}
    assert set(row["chain_inputs"]) == {"Chain.Dockerfile", "solc.json", "rpc_filter.py"}
