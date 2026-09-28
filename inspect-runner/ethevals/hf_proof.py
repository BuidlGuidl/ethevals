"""Exercise Inspect's stock HF task loader with local files and mock outputs."""

import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import yaml
from inspect_ai import eval, task_with
from inspect_ai._eval.task import hf
from inspect_ai.dataset import json_dataset
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model

from .checks import check_player, check_grader
from .config import Config
from .loader import Eval
from .rows import results_rows
from .runner import build_task
from .scorers import target_reference


def local_hf_tasks(export: Path, task_id: str | None = None):
    """Replace only Hub I/O and its dependency check; keep Inspect's task creation."""
    card = yaml.safe_load((export / "README.md").read_text().split("---", 2)[1])
    paths = {item["config_name"]: export / item["data_files"][0]["path"] for item in card["configs"]}

    def download(*, repo_id, filename, repo_type, revision):
        if filename != "eval.yaml" or repo_type != "dataset":
            raise ValueError(f"Unexpected HF download: {filename}")
        return str(export / filename)

    def dataset(*, path, revision, name, split, sample_fields):
        if split != "test":
            raise ValueError(f"Unexpected HF split: {split}")
        return json_dataset(str(paths[name]), sample_fields=sample_fields)

    hub = ModuleType("huggingface_hub")
    hub.hf_hub_download = download
    hub.errors = SimpleNamespace(EntryNotFoundError=FileNotFoundError)
    with patch.dict("sys.modules", {"huggingface_hub": hub}), \
            patch.object(hf, "verify_required_version"), patch.object(hf, "hf_dataset", dataset):
        return hf.task_create_from_hf("hf/local/ethevals" + (f"/{task_id}" if task_id else ""))


def prove(export: Path, evaluations: list[Eval], output: Path, config: Config) -> list[dict]:
    if output.resolve().is_relative_to(export.resolve()):
        raise ValueError("Proof output must stay outside the HF export directory")
    evaluations = {evaluation.id: evaluation for evaluation in evaluations}
    card = yaml.safe_load((export / "README.md").read_text().split("---", 2)[1])
    paths = {item["config_name"]: export / item["data_files"][0]["path"] for item in card["configs"]}
    declarations = yaml.safe_load((export / "eval.yaml").read_text())["tasks"]
    tasks = local_hf_tasks(export)
    report = []
    for declaration, stock in zip(declarations, tasks, strict=True):
        direct = json_dataset(str(paths[declaration["config"]]))
        for sample, hf_sample in zip(direct, stock.dataset, strict=True):
            evaluation = evaluations[sample.id]
            reference = target_reference(evaluation.scorers[0], evaluation.declaration)
            for answer_kind, answer in [("reference", reference), ("wrong", "An incorrect answer.")]:
                observed = {"config": declaration["config"], "eval_id": sample.id, "answer": answer_kind}

                def model():
                    return get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", answer)])

                for route, exported_sample in [("json_dataset", sample), ("hf_loader", hf_sample)]:
                    task = task_with(stock, dataset=[exported_sample], model=model())
                    log = read_eval_log(eval(task, log_dir=str(output / "logs"), display="none")[0].location)
                    if log.status != "success" or not log.samples or len(log.samples[0].scores or {}) != 1:
                        raise ValueError(f"{sample.id}: {route} did not produce one score: {log.error}")
                    observed[route] = next(iter(log.samples[0].scores.values())).value
                runner = build_task(evaluation, config, check_player(evaluation, "reference"),
                                    check_grader(), "vanilla", 1)
                runner.model = model()
                log = read_eval_log(eval(runner, log_dir=str(output / "logs"), display="none")[0].location)
                rows = results_rows(log)
                if len(rows) != 1 or rows[0]["passed"] is None:
                    raise ValueError(f"{sample.id}: runner did not produce one verdict: {rows}")
                observed["runner"] = "C" if rows[0]["passed"] else "I"
                report.append(observed)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    for row in report:
        expected = "C" if row["answer"] == "reference" else "I"
        if any(row[route] != expected for route in ("json_dataset", "hf_loader", "runner")):
            raise ValueError(f"HF parity mismatch: {row}")
    return report
