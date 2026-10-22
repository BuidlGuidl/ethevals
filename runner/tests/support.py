from pathlib import Path
import json
import os
import shutil
import subprocess
import sys


def recorded_trial(folder: Path, task: Path) -> None:
    """Replay a recorded result with Harbor's lock for the supplied task."""
    from harbor.models.task.task import Task
    from harbor.publisher.packager import Packager

    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    (folder / "lock.json").write_text(json.dumps({"task": {
        "name": Task(task).name, "type": "local", "digest": "sha256:" + Packager.compute_content_hash(task)[0],
    }}))


def cli(*args):
    environment = {key: value for key, value in os.environ.items() if key not in {
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY", "GH_TOKEN", "HF_TOKEN",
        "PYTEST_CURRENT_TEST"}}
    return subprocess.run([sys.executable, *map(str, args)], cwd=Path(__file__).resolve().parents[2], env=environment,
                          capture_output=True, text=True, timeout=60)
