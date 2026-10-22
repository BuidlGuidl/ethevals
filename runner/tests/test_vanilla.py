import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

from harbor.agents.factory import AgentFactory
from harbor.models.agent.context import AgentContext
from harbor.models.trial.config import AgentConfig
from harbor.models.trajectories import Trajectory
import pytest

from support import cli


@contextmanager
def stand_in(reply="metre", status=200, host="127.0.0.1"):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            payload = {"id": "local-completion", "object": "chat.completion", "created": 1,
                       "model": request["model"], "choices": [{"index": 0, "finish_reason": "stop",
                       "message": {"role": "assistant", "content": reply(request) if callable(reply) else reply}}],
                       "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
                                 "prompt_tokens_details": {"cached_tokens": 40}}}
            if status != 200:
                payload = {"error": {"message": "Local stand-in refused the request.", "type": "server_error"}}
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((host, 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"api_base": f"http://127.0.0.1:{server.server_port}/v1", "api_key": "local-stand-in"}, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("model", ["openai/first-model", "openai/another-model"])
def test_bare_model_gets_one_instruction_without_tools_or_environment(tmp_path, model):
    with stand_in() as (completion, requests):
        agent = AgentFactory.create_agent_from_config(AgentConfig(
            name="ethevals.vanilla:VanillaAgent", model_name=model,
            kwargs={"version": "9.8.7", "reasoning_effort": "high", "completion": completion}), logs_dir=tmp_path)
        context = AgentContext()
        # Any environment access fails because this object has no environment methods.
        asyncio.run(agent.setup(object()))
        asyncio.run(agent.run("Name a unit.", object(), context))
    assert requests == [{"model": model.removeprefix("openai/"),
                         "messages": [{"role": "user", "content": "Name a unit."}], "reasoning_effort": "high"}]
    trajectory = Trajectory.model_validate_json((tmp_path / "trajectory.json").read_text())
    assert [(step.source, step.message) for step in trajectory.steps] == [("user", "Name a unit."), ("agent", "metre")]
    assert (trajectory.agent.model_name, trajectory.agent.tool_definitions) == (model, [])
    assert (agent.version(), trajectory.agent.version) == ("9.8.7", "9.8.7")
    assert (context.n_input_tokens, context.n_cache_tokens, context.n_output_tokens, context.cost_usd) == (100, 40, 10, None)


def test_model_error_does_not_retry_or_write_a_reply(tmp_path):
    import litellm

    with stand_in(status=503) as (completion, requests):
        agent = AgentFactory.create_agent_from_config(AgentConfig(
            name="ethevals.vanilla:VanillaAgent", model_name="openai/first-model",
            kwargs={"completion": completion}), logs_dir=tmp_path)
        with pytest.raises(litellm.ServiceUnavailableError):
            asyncio.run(agent.run("Name a unit.", object(), AgentContext()))
    assert requests == [{"model": "first-model", "messages": [{"role": "user", "content": "Name a unit."}]}]
    assert not (tmp_path / "trajectory.json").exists()


@pytest.mark.parametrize("option", ["tools", "messages", "fallbacks", "num_retries"])
def test_completion_options_cannot_add_tools_or_calls(tmp_path, option):
    with pytest.raises(ValueError, match="cannot override"):
        AgentFactory.create_agent_from_config(AgentConfig(
            name="ethevals.vanilla:VanillaAgent", model_name="openai/first-model",
            kwargs={"completion": {option: []}}), logs_dir=tmp_path)


@pytest.mark.docker
@pytest.mark.parametrize("model", ["openai/first-model", "openai/another-model"])
def test_vanilla_quiz_through_harbor_and_board_rows(tmp_path, model):
    import shutil
    from ethevals.jobs import task_entry

    task = tmp_path / "concepts/question"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/concepts/question", task)
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace('modes = ["internet"]', 'modes = ["vanilla"]'))
    output, config = tmp_path / "out", tmp_path / "job.json"
    with stand_in(reply="metre") as (completion, requests):
        config.write_text(json.dumps({
            "harbor_version": "0.24.0", "n_attempts": 1, "modes": ["vanilla"],
            "models": {"configured": {"name": model, "effort": "high", "kwargs": {"completion": completion}}},
            "agents": {"bare": {"name": "ethevals.vanilla:VanillaAgent", "version": "0.1.0",
                                  "model": "configured", "modes": ["vanilla"], "paid_by": "free", "cost_limit_usd": 0}}}))
        result = cli("-m", "ethevals.cli", "run", "--config", config, "--tasks", task,
                     "--budget", 0, "--output", output, "--rows", tmp_path / "none")
    assert result.returncode == 0, result.stdout + result.stderr
    assert requests == [{"model": model.removeprefix("openai/"), "reasoning_effort": "high",
                         "messages": [{"role": "user", "content": (task / "instruction.md").read_text()}]}]
    row = json.loads((output / "rows.jsonl").read_text())
    assert (row["task_id"], row["mode"], row["agent"], row["model"], row["status"], row["model_cost_usd"]) == (
        task_entry(task)["id"], "vanilla", None, model, "passed", 0)
    assert (row["total_tokens"], row["paid_by"]) == (110, "free")
    assert row["checks"] == {"unit": {"passed": True, "reason": "The final reply matches."}}
    trajectory = Trajectory.model_validate_json(Path(row["trajectory_file"]).read_text())
    assert trajectory.steps[-1].message == "metre"
    trial = json.loads(next((output / "jobs").glob("*/*/result.json")).read_text())
    assert trial["verifier_environment_mode"] == "separate"
    assert trial["verifier_result"] == {"rewards": {"reward": 1.0}}
