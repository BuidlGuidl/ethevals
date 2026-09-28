"""Export vanilla quizzes as a local Hugging Face dataset repository."""

import hashlib
import json
import re
from pathlib import Path

import yaml

from .loader import Eval

DEFAULT_REPO = "ethereum-foundation/hf-ethevals-dataset"


def write_hf(evals: list[Eval], output: Path, repo: str = DEFAULT_REPO,
             license: str | None = None) -> dict:
    if not re.fullmatch(r"[\w-]+/[\w.-]+", repo):
        raise ValueError("HF repo must have the form owner/name")
    groups = {}
    for evaluation in sorted(evals, key=lambda item: item.id):
        if evaluation.declaration.type != "quiz" or "vanilla" not in evaluation.declaration.modes:
            continue
        if len(evaluation.scorers) != 1 or evaluation.scorers[0].kind != "target":
            raise ValueError(f"{evaluation.id}: HF export requires exactly one target scorer")
        config = evaluation.scorers[0]
        target = config.target
        if isinstance(target, list):
            if len(target) != 1:
                raise ValueError(f"{evaluation.id}: Inspect's HF loader cannot preserve alternative targets; export stopped")
            target = target[0]
        if config.method == "match":
            args = {"location": config.location, "ignore_case": config.ignore_case, "numeric": config.numeric}
        elif config.method == "pattern":
            args = {"pattern": config.pattern, "ignore_case": config.ignore_case}
        else:
            args = {}
        scorer = {"name": config.method, "args": args}
        digest = hashlib.sha256(json.dumps(scorer, sort_keys=True).encode()).hexdigest()[:12]
        name = f"{evaluation.pillar}-{config.method}-{digest}"
        if name not in groups:
            fields = {"input": "input", "target": "target", "metadata": ["metadata"]}
            if evaluation.declaration.choices:
                fields["choices"] = "choices"
            groups[name] = {"rows": [], "task": {
                "id": name, "config": name, "split": "test", "field_spec": fields,
                "solvers": [{"name": "multiple_choice" if evaluation.declaration.choices else "generate"}],
                "scorers": [scorer],
            }}
        groups[name]["rows"].append({
            "id": evaluation.id, "input": evaluation.declaration.prompt,
            "target": target, "choices": evaluation.declaration.choices,
            "metadata": {"eval_id": evaluation.id, "pillar": evaluation.pillar, "eval_hash": evaluation.hash},
        })
    if not groups:
        raise ValueError("No quiz evals declare vanilla mode")
    # Reject before writing so an unsupported quiz cannot leave a partial dataset.
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"{output}: HF export requires an empty output directory")
    configs = [{"config_name": name, "data_files": [{"split": "test", "path": f"data/{name}/test.jsonl"}]} for name in sorted(groups)]
    card = {"pretty_name": "ETH Evals", "language": ["en"], "task_categories": ["question-answering"],
            "tags": ["ethereum", "inspect-ai"], "size_categories": ["n<1K"], "configs": configs}
    count = sum(len(group["rows"]) for group in groups.values())
    if count >= 1000:
        card.pop("size_categories")
    if license:
        card["license"] = license
    tasks = [groups[name]["task"] for name in sorted(groups)]
    for config in configs:
        path = output / config["data_files"][0]["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                for row in groups[config["config_name"]]["rows"]))
    (output / "eval.yaml").write_text(yaml.safe_dump({
        "name": "ETH Evals", "description": "Vanilla Ethereum quizzes.",
        "evaluation_framework": "inspect-ai", "tasks": tasks,
    }, sort_keys=False))
    first = configs[0]["config_name"]
    license_text = f"Dataset license: `{license}`." if license else "Dataset license is undecided. Choose it before publication."
    (output / "README.md").write_text("---\n" + yaml.safe_dump(card, sort_keys=False) + "---\n\n" + f"""# ETH Evals

This dataset contains {count} Ethereum quiz evals that declare the vanilla mode.
Each row holds one prompt and its target. Builds and agent modes stay in the source repository.
{license_text}

`id` identifies the eval. `input`, `target`, and `choices` use Inspect's sample fields.
`metadata` holds `eval_id`, `pillar`, and `eval_hash`. The hash covers every file in the source eval folder.
The export contains no logs, workspace files, or build solutions.

Each config groups one pillar and one set of scorer settings.
Its suffix identifies those settings. `eval.yaml` names the solver and scorer for each config.
Match tasks set their location explicitly. Choice tasks use `multiple_choice` and `choice`.
The export rejects alternative target lists because Inspect's HF loader changes their meaning.
A single-item target list becomes its string value.

Load a config without a field mapping:

```python
from inspect_ai.dataset import hf_dataset

dataset = hf_dataset("{repo}", name="{first}", split="test")
```

Install Inspect's optional `datasets` dependency to use `hf_dataset`.
For a local copy, `json_dataset("data/{first}/test.jsonl")` needs no extra package.
Choose a config from the card's `configs` list. Each config has one `test` split.
Pass `revision` to `hf_dataset` to pin a published version.

After publication, run all benchmark tasks with stock Inspect:

```sh
inspect eval hf/{repo} --model YOUR_PROVIDER/YOUR_MODEL
```

That command calls the selected model. It needs the provider's credentials and can incur charges.
Install `huggingface_hub` and `datasets` for the `hf/` task loader.
The `hf/` loader reads the same prompt, choices, target, and scoring settings.
Inspect 0.3.271 assigns sample IDs on that path and nests the source metadata under `metadata`.
Direct `hf_dataset` and `json_dataset` loads retain the row ID and metadata without a mapping.

These public targets can appear in training data. Scores on them alone do not establish unseen Ethereum knowledge.
""")
    return {"repo": repo, "output": str(output), "rows": count,
            "configs": [config["config_name"] for config in configs], "license": license}
