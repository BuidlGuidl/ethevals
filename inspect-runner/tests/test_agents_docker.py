from pathlib import Path
import os
import subprocess
import sys

import pytest



@pytest.mark.docker
@pytest.mark.parametrize("agent", ["claude-code-opus-5.5", "codex-cli-gpt-5.5", "opencode-kimi-k3", "opencode-glm-5.3"])
@pytest.mark.parametrize("answer", ["reference", "empty"])
@pytest.mark.parametrize("evaluation,mode", [
    ("building/erc20-points-token", "internet"),
    ("concepts/agent-registries", "internet"),
    ("concepts/agent-registries", "skills"),
])
def test_agent_proof(tmp_path, agent, answer, evaluation, mode):
    environment = os.environ.copy()
    for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY"):
        environment.pop(name, None)
    proof = Path(__file__).with_name("prove_agent.py")
    command = [sys.executable, str(proof), answer, "--agent", agent, "--eval", "evals/" + evaluation,
               "--mode", mode, "--output", str(tmp_path / "proof")]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=300)
    (tmp_path / "proof.txt").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, (result.stdout + result.stderr)[-12000:]


@pytest.mark.docker
@pytest.mark.parametrize("agent", ["claude-code-opus-5.5", "codex-cli-gpt-5.5", "opencode-kimi-k3"])
def test_exa_key_stays_out_of_each_harness_archive(tmp_path, agent):
    environment = os.environ.copy()
    for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY"):
        environment.pop(name, None)
    proof = Path(__file__).with_name("prove_agent.py")
    result = subprocess.run([sys.executable, str(proof), "empty", "--agent", agent, "--exa-canary",
                             "--output", str(tmp_path / "proof")], env=environment,
                            capture_output=True, text=True, timeout=300)
    (tmp_path / "proof.txt").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, (result.stdout + result.stderr)[-12000:]
