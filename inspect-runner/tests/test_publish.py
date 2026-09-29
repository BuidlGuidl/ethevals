from pathlib import Path
import json
import subprocess
import sys

from ethevals.loader import load_eval
from ethevals.publish import publish_logs
import pytest

from conftest import fixture_config


ROOT = Path(__file__).resolve().parents[2]
EVALUATION = load_eval(ROOT / "evals/concepts/agent-registries", fixture_config())


def local_results(tmp_path):
    (tmp_path / "logs").mkdir()
    for name in ["old.eval", "kept.eval", "unused.eval"]:
        (tmp_path / "logs" / name).write_bytes(b"log fixture")
    rows = [{"eval_id": EVALUATION.id, "eval_hash": EVALUATION.hash,
             "status": "passed", "model": "test/model", "mode": "vanilla", "epoch": epoch,
             "log_file": "logs/kept.eval"} for epoch in [1, 2]]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows


def test_publish_dry_run_picks_only_referenced_logs_and_writes_nothing(tmp_path):
    rows = local_results(tmp_path)
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "publish-logs", "--output", str(tmp_path),
                             "--repo", "example/ethevals", "--run-id", "123-1", "--commit", "a" * 40],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert (plan["dry_run"], plan["release"]) == (True, "results-123-1")
    assert [(asset["name"], asset["url"], [row["epoch"] for row in asset["rows"]]) for asset in plan["assets"]] == [
        ("kept.eval", "https://github.com/example/ethevals/releases/download/results-123-1/kept.eval", [1, 2])]
    assert not (tmp_path / "published").exists()
    assert [json.loads(line) for line in (tmp_path / "rows.jsonl").read_text().splitlines()] == rows
    assert plan["command"][:4] == ["gh", "release", "create", "results-123-1"]
    assert plan["command"][-1] == str(tmp_path / "logs/kept.eval")


@pytest.mark.parametrize("file", ["../secret.eval", "/secret.eval", "logs/missing.eval", "logs/bad name.eval"])
def test_publish_rejects_missing_or_unsafe_logs(tmp_path, file):
    rows = local_results(tmp_path)
    rows[0]["log_file"] = file
    (tmp_path / "rows.jsonl").write_text(json.dumps(rows[0]) + "\n")
    with pytest.raises(ValueError, match="row 1:"):
        publish_logs(tmp_path, "example/ethevals", "1", "a" * 40)
    (tmp_path / "rows.jsonl").write_text(json.dumps(rows[1]) + "\n")
    assert publish_logs(tmp_path, "example/ethevals", "1", "a" * 40)["assets"][0]["name"] == "kept.eval"


def test_publish_stages_rows_only_after_the_release_command_succeeds(tmp_path, monkeypatch):
    rows = local_results(tmp_path)
    dry = publish_logs(tmp_path, "example/ethevals", "dry", "a" * 40)
    assert dry["release"] == "results-dry"
    def failed(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr("ethevals.publish.subprocess.run", failed)
    with pytest.raises(subprocess.CalledProcessError):
        publish_logs(tmp_path, "example/ethevals", "1", "a" * 40, publish=True)
    assert not list((tmp_path / "published").glob("*.jsonl"))
    receipt = []
    def succeeded(command, **kwargs):
        receipt.append(command)
        return subprocess.CompletedProcess(command, 0, "release fixture")
    monkeypatch.setattr("ethevals.publish.subprocess.run", succeeded)
    plan = publish_logs(tmp_path, "example/ethevals", "1", "a" * 40, publish=True)
    assert Path(plan["rows_file"]).name == "results-1.jsonl"
    assert [json.loads(line) for line in Path(plan["rows_file"]).read_text().splitlines()] == [
        {**row, "log_url": "https://github.com/example/ethevals/releases/download/results-1/kept.eval"} for row in rows]
    assert receipt[0][:10] == ["gh", "release", "create", "results-1", "--repo", "example/ethevals",
                               "--target", "a" * 40, "--latest=false", "--title"]


def test_hash_in_output_path_cannot_select_an_unrelated_file(tmp_path):
    (tmp_path / "job").write_text("unrelated private file")
    output = tmp_path / "job#1"
    output.mkdir()
    local_results(output)
    with pytest.raises(ValueError, match="#"):
        publish_logs(output, "example/ethevals", "1", "a" * 40)


def test_reused_folder_skips_published_and_hidden_rows(tmp_path, monkeypatch):
    rows = local_results(tmp_path)
    monkeypatch.setattr("ethevals.publish.subprocess.run", lambda *args, **kwargs: None)
    publish_logs(tmp_path, "example/ethevals", "first", "a" * 40, publish=True)
    (tmp_path / "logs/new.eval").write_bytes(b"new log")
    rows += [{**rows[0], "epoch": epoch, **change} for epoch, change in enumerate([
        {"log_url": "https://github.com/example/ethevals/releases/download/results-elsewhere/linked.eval"},
        {"eval_hash": "old", "log_file": "logs/new.eval"},
        {"mode": "skills", "log_file": "logs/new.eval"},
        {"log_file": "logs/new.eval"},
    ], 3)]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    plan = publish_logs(tmp_path, "example/ethevals", "second", "a" * 40)
    assert [(asset["name"], [row["epoch"] for row in asset["rows"]]) for asset in plan["assets"]] == [("new.eval", [4, 5, 6])]
    assert plan["skipped"] == {"published": 3}
    assert sorted(path.name for path in (tmp_path / "published").iterdir()) == ["results-first.jsonl"]
