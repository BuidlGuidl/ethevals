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
    guide = Path(__file__).with_name("hf_readme.md").read_text().replace(
        f"https://huggingface.co/datasets/{DEFAULT_REPO}", f"https://huggingface.co/datasets/{repo}",
    ).format(requirements="\n".join(requirements) or "These tasks need no host variables.")
    (output / "README.md").write_text("---\n" + yaml.safe_dump(card, sort_keys=False) + "---\n\n" + guide)
    return {"repo": repo, "output": str(output), "tasks": len(tasks), "license": license}
