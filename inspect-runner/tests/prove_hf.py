"""Run exported HF task settings through stock Inspect without Hub access."""

import argparse
import json
from pathlib import Path

import yaml
from inspect_ai import Task, eval
from inspect_ai._eval.task.hf import HFTask, _record_to_sample_hf
from inspect_ai.dataset import json_dataset
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model
import inspect_ai.scorer as scorers
import inspect_ai.solver as solvers

from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.rows import results_rows
from ethevals.scorers import target_reference
from support import build_task


def prove(export: Path, folders: list[Path], output: Path) -> list[dict]:
    config = load_config()
    evaluations = {evaluation.id: evaluation for evaluation in (load_eval(folder, config) for folder in folders)}
    card = yaml.safe_load((export / "README.md").read_text().split("---", 2)[1])
    paths = {item["config_name"]: export / item["data_files"][0]["path"] for item in card["configs"]}
    report = []
    for declaration in yaml.safe_load((export / "eval.yaml").read_text())["tasks"]:
        spec = HFTask.model_validate(declaration)
        path = paths[spec.config]
        direct = json_dataset(str(path))  # No mapping: use Inspect's default columns.
        records = [json.loads(line) for line in path.read_text().splitlines()]
        for sample, record in zip(direct, records, strict=True):
            evaluation = evaluations[sample.id]
            reference = target_reference(evaluation.scorers[0], evaluation.declaration)
            for answer_kind, answer, expected in [("reference", reference, "C"), ("wrong", "An incorrect answer.", "I")]:
                def model():
                    return get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", answer)])

                # Use the same constructors and args named by the HF benchmark file.
                for route, exported_sample in [("json_dataset", sample),
                                                ("hf_loader", _record_to_sample_hf(record, spec.field_spec))]:
                    task = Task(name=f"hf-{route}-{answer_kind}", dataset=[exported_sample],
                                solver=[getattr(solvers, item.name)(**item.args) for item in spec.solvers],
                                scorer=[getattr(scorers, item.name)(**item.args) for item in spec.scorers], model=model())
                    log = eval(task, log_dir=str(output / "logs"), display="none")[0]
                    log = read_eval_log(log.location)
                    assert log.status == "success", log.error
                    actual = [score.value for score in log.samples[0].scores.values()]
                    assert actual == [expected], (spec.id, route, answer_kind, actual)
                runner = build_task(evaluation, config, None, "vanilla", "reference", 1)
                runner.model = model()
                log = eval(runner, log_dir=str(output / "logs"), display="none")[0]
                rows = results_rows(read_eval_log(log.location))
                assert [row["passed"] for row in rows] == [expected == "C"], rows
                report.append({"config": spec.config, "eval_id": sample.id, "answer": answer_kind,
                               "json_dataset": expected, "hf_loader": expected, "runner": expected})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prove(args.export, sorted(Path("evals").glob("*/*")), args.output), indent=2))
