from pathlib import Path
import os
import subprocess
import sys


def cli(*args):
    environment = {key: value for key, value in os.environ.items() if key not in {
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY", "GH_TOKEN", "HF_TOKEN",
        "PYTEST_CURRENT_TEST"}}
    return subprocess.run([sys.executable, *map(str, args)], cwd=Path(__file__).resolve().parents[2], env=environment,
                          capture_output=True, text=True, timeout=60)
