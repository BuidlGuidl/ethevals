"""A local agent for job, billing, and time-limit proofs."""
import asyncio
import json
import shlex

from harbor.agents.nop import NopAgent
from harbor.agents.capabilities import AgentCapabilities


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


class SkillsAgent(LocalAgent):
    capabilities = AgentCapabilities(skills=True)

    def __init__(self, *args, skills_dir=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.skills_dir = skills_dir

    async def run(self, instruction, environment, context):
        script = f"""
import json
from pathlib import Path
root = Path({self.skills_dir!r}) if {self.skills_dir!r} else None
files = {{path.relative_to(root).as_posix(): path.read_bytes().hex()
         for path in root.rglob('*') if path.is_file()}} if root else {{}}
Path('/logs/agent/skills.json').write_text(json.dumps({{'directory': {self.skills_dir!r}, 'files': files}}))
"""
        result = await environment.exec(command="python3 -c " + shlex.quote(script))
        if result.return_code != 0:
            raise RuntimeError(result.stderr)
        await super().run(instruction, environment, context)
