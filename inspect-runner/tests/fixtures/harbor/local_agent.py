"""A local agent for job, billing, and time-limit proofs."""
import asyncio
import json
import shlex

from harbor.agents.nop import NopAgent


class LocalAgent(NopAgent):
    @staticmethod
    def name():
        return "local-agent"

    def __init__(self, *args, delay=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.delay = delay

    async def run(self, instruction, environment, context):
        trajectory = json.dumps({
            "schema_version": "ATIF-v1.7", "session_id": "local-agent",
            "agent": {"name": self.name(), "version": self.version()},
            "steps": [{"step_id": 1, "source": "agent", "message": "metre"}],
        })
        await environment.exec(command="mkdir -p /logs/agent; printf %s " + shlex.quote(trajectory)
                               + " > /logs/agent/trajectory.json")
        context.n_input_tokens = 100
        context.n_cache_tokens = 40
        context.n_output_tokens = 10
        context.cost_usd = 0.01234
        await asyncio.sleep(self.delay)
