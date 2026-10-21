"""Copy Harbor task folders into a Hugging Face dataset repository."""
import json
from pathlib import Path
import re
import shutil

import yaml

from .harbor_tasks import lint_task

DEFAULT_REPO = "buidlguidl/ethevals-test"


def write_hf(paths: list[Path], output: Path, repo: str = DEFAULT_REPO,
             license: str | None = None) -> dict:
    if not re.fullmatch(r"[\w-]+/[\w.-]+", repo):
        raise ValueError("HF repo must have the form owner/name")
    if not paths:
        raise ValueError("No task folders found")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"{output}: HF export requires an empty output directory")
    tasks = []
    for path in sorted(paths):
        lint_task(path)
        name = f"{path.parent.name}--{path.name}"
        if any(task["name"] == name for task in tasks):
            raise ValueError(f"{path}: duplicate published task name {name}")
        tasks.append({"name": name, "path": f"tasks/{name}"})
    # Check every folder before copying; publication never rewrites task files.
    for path, task in zip(sorted(paths), tasks, strict=True):
        shutil.copytree(path, output / task["path"])
    (output / "registry.json").write_text(json.dumps([{
        "name": "ethevals", "version": "1.0", "description": "Ethereum tasks.", "tasks": tasks,
    }], indent=2) + "\n")
    (output / "eval.yaml").write_text(yaml.safe_dump({
        "name": "ETH Evals", "evaluation_framework": "harbor", "tasks": tasks,
    }, sort_keys=False))
    card = {"pretty_name": "ETH Evals", "language": ["en"],
            "tags": ["ethereum", "rl-environment", "harbor"]}
    if license:
        card["license"] = license
    (output / "README.md").write_text("---\n" + yaml.safe_dump(card, sort_keys=False) + "---\n\n" + f"""# ETH Evals

This dataset contains {len(tasks)} Ethereum tasks in Harbor format.
Each folder contains its instruction, environment, tests, and solution.
The files match the source task folder byte for byte.
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

Tasks declare required host variables in `metadata.required_env` in `task.toml`.
Set those variables before running the selected tasks.
Plain Harbor runs execute each task's verifier. The board also runs paid criteria through RewardKit when declared.
These public solutions can appear in training data. Scores alone do not establish unseen Ethereum knowledge.
""")
    return {"repo": repo, "output": str(output), "tasks": len(tasks), "license": license}
