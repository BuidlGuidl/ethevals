"""Copy Harbor task folders into a Hugging Face dataset repository."""
import json
from pathlib import Path
import re
import shutil

from harbor.models.task.task import Task
from harbor.publisher.packager import Packager
import yaml

from .harbor_tasks import lint_task, task_host_variables

DEFAULT_REPO = "buidlguidl/ethevals-test"
DESCRIPTION = "Tasks that measure how well AI agents do Ethereum work and what bare models know about Ethereum."


def write_hf(paths: list[Path], output: Path, repo: str = DEFAULT_REPO,
             license: str | None = None) -> dict:
    if not re.fullmatch(r"[\w-]+/[\w.-]+", repo):
        raise ValueError("HF repo must have the form owner/name")
    if not paths:
        raise ValueError("No task folders found")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"{output}: HF export requires an empty output directory")
    tasks, requirements = [], []
    for path in sorted(paths):
        lint_task(path)
        name = Task(path).name
        if any(task["name"] == name for task in tasks):
            raise ValueError(f"Duplicate task name: {name}")
        tasks.append({"name": name, "path": f"tasks/{path.parent.name}--{path.name}"})
        if variables := task_host_variables(path):
            requirements.append(f"- `{name}`: " + ", ".join(f"`{variable}`" for variable in variables))
    # Check every folder before copying; publication never rewrites task files.
    for path, task in zip(sorted(paths), tasks, strict=True):
        for file in Packager.collect_files(path):
            destination = output / task["path"] / file.relative_to(path.resolve())
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
    (output / "registry.json").write_text(json.dumps([{
        "name": "ethevals", "version": "1.0", "description": DESCRIPTION, "tasks": tasks,
    }], indent=2) + "\n")
    (output / "eval.yaml").write_text(yaml.safe_dump({
        "name": "ETH Evals", "description": DESCRIPTION, "evaluation_framework": "harbor",
        "tasks": [{"id": "ethevals", "config": "default", "split": "test"}],
    }, sort_keys=False))
    card = {"pretty_name": "ETH Evals", "language": ["en"],
            "tags": ["ethereum", "rl-environment", "harbor"]}
    if license:
        card["license"] = license
    (output / "README.md").write_text("---\n" + yaml.safe_dump(card, sort_keys=False) + "---\n\n" + f"""# ETH Evals

This dataset contains {len(tasks)} Ethereum tasks in Harbor format.
Each folder contains its instruction, environment, tests, and solution.
The export contains exactly the files Harbor's packager counts, with their bytes unchanged.
Each task's `[task].name` stays the same in the source folder, registry, and Harbor trials.
Shared images use pinned GHCR tags. ETH Evals code is not required.

Install Harbor 0.24.0 and Docker, then run an oracle check:

```sh
harbor run --repo https://huggingface.co/datasets/{repo} --agent oracle --n-concurrent 1
```

Use `--include-task-name NAME` to select one folder name under `tasks/`.
Use `--agent nop` to check that untouched work fails.
Use `--dataset ethevals@1.0` to select the explicit registry entry.
Append `@gh-SHORT_SHA` to the repository URL to pin a published source revision.
The registry resolves task paths against the selected dataset commit.

Each task's compose file declares its host variables through `${{VAR:?message}}` interpolation.
Set those variables before running the task. Compose stops with the message if a value is missing or empty.

{chr(10).join(requirements)}

Plain Harbor runs execute every test and criterion through RewardKit in the task's verifier.
Tasks with a judge TOML under `tests/` require `ANTHROPIC_API_KEY` through `[verifier.env]`.
Set a judge-only API key with its own spend limit. A missing key stops Harbor with the variable's name.
Claude plan tokens cannot pay for the judge.
The task's judge is the default; the board overrides its model and effort from the job config.
These public solutions can appear in training data. Scores alone do not establish unseen Ethereum knowledge.
""")
    return {"repo": repo, "output": str(output), "tasks": len(tasks), "license": license}
