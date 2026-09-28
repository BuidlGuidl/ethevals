"""Run each real CLI against mock replies and one keyless Exa search."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.docker
@pytest.mark.parametrize("model", ["opus", "codex", "kimi", "glm"])
@pytest.mark.parametrize("answer", ["reference", "empty"])
def test_agent_proof(tmp_path, model, answer):
    environment = os.environ.copy()
    for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        environment.pop(name, None)
    proof = Path(__file__).with_name("prove_agent.py")
    command = [sys.executable, str(proof), answer, "--model", model, "--output", str(tmp_path / "proof")]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=300)
    (tmp_path / "proof.txt").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, (result.stdout + result.stderr)[-12000:]
