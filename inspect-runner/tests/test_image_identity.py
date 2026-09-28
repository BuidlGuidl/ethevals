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


@pytest.mark.parametrize("image,eval_path", [
    ("runner", "building/erc20-points-token"),
    ("chain", "transactions/send-six-decimal-token"),
])
def test_build_inputs_rename_images_and_grading_config_only_invalidates_checks(tmp_path, monkeypatch, image, eval_path):
    import ethevals.preparation as preparation
    import ethevals.sandboxes as sandboxes

    images = tmp_path / "images"
    shutil.copytree(IMAGES, images)
    monkeypatch.setattr(preparation, "IMAGES", images)
    monkeypatch.setattr(sandboxes, "IMAGES", images)
    evaluation = load_eval(ROOT / "evals" / eval_path, load_config())
    compose = images / ("act.compose.yaml" if image == "chain" else "stock.compose.yaml")
    original = image_tag(images, image)
    cache = check_cache_path(evaluation, tmp_path, compose)
    foundry = images / "foundry.toml"
    foundry.write_text(foundry.read_text() + "optimizer = true\n")
    assert image_tag(images, image) == original
    assert check_cache_path(evaluation, tmp_path, compose) != cache

    for name in BUILD_INPUTS[image]:
        before = image_tag(images, image)
        cache = check_cache_path(evaluation, tmp_path, compose)
        path = images / name
        path.write_bytes(path.read_bytes() + b"\n")
        assert image_tag(images, image) != before
        assert check_cache_path(evaluation, tmp_path, compose) != cache
        with pytest.raises(ValueError, match="requires the .* image"):
            prepare_compose(evaluation, tmp_path / "stale")
        path.write_bytes(path.read_bytes()[:-1])


def test_both_compose_files_declare_the_computed_images():
    for name in ("stock.compose.yaml", "act.compose.yaml"):
        services = yaml.safe_load((IMAGES / name).read_bytes())["services"]
        assert services["default"]["image"] == services["scorer"]["image"] == image_tag(IMAGES)
        if "chain" in services:
            assert services["chain"]["image"] == image_tag(IMAGES, "chain")


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
    task = build_task(evaluation, config, check_player(evaluation, "empty"), check_grader(), "internet", 1)
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
