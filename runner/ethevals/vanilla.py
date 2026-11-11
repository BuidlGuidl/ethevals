"""Answer an instruction with one model call and no tools."""
import json
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.agents.capabilities import AgentCapabilities
from harbor.agents.options import AgentOptions
from harbor.models.trajectories import Agent, Metrics, Step, Trajectory
import litellm
from pydantic import Field, field_validator

VERSION = "0.1.0"

class VanillaOptions(AgentOptions):
    version: str = VERSION
    reasoning_effort: str | None = None
    completion: dict[str, Any] = Field(default_factory=dict)

    @field_validator("completion")
    @classmethod
    def check_completion(cls, value):
        reserved = {"model", "messages", "tools", "tool_choice", "functions", "function_call",
                    "stream", "num_retries", "max_retries", "fallbacks", "reasoning_effort"}
        if reserved & value.keys():
            raise ValueError("Completion options cannot override the model, instruction, tools, retries, or effort.")
        return value


class VanillaAgent(BaseAgent):
    capabilities = AgentCapabilities(atif=True, reasoning_effort=True)
    options_model = VanillaOptions

    @staticmethod
    def name():
        return "vanilla"

    def version(self):
        return self.options.version

    async def setup(self, environment):
        pass

    async def run(self, instruction, environment, context):
        options = self.options
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        try:
            response = await litellm.acompletion(
                model=self.model_name, messages=[{"role": "user", "content": instruction}],
                reasoning_effort=options.reasoning_effort, num_retries=0, max_retries=0,
                **options.completion,
            )
        except litellm.ContentPolicyViolationError as error:
            (self.logs_dir / "provider.json").write_text(json.dumps({
                "stop_reason": type(error).__name__, "refused": True}) + "\n")
            raise
        message = response.choices[0].message
        provider = getattr(message, "provider_specific_fields", None) or {}
        stop_reason = provider.get("stop_reason") or response.choices[0].finish_reason
        refused = bool(getattr(message, "refusal", None)) or stop_reason in {"content_filter", "refusal", "safety", "blocked"}
        (self.logs_dir / "provider.json").write_text(json.dumps({
            "stop_reason": stop_reason,
            "refused": refused,
        }) + "\n")
        usage = response.usage
        context.n_input_tokens = usage.prompt_tokens
        context.n_output_tokens = usage.completion_tokens
        context.n_cache_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
        context.cost_usd = response._hidden_params.get("response_cost")
        if context.cost_usd is None:
            try:
                context.cost_usd = litellm.completion_cost(completion_response=response)
            except Exception:
                # Unknown model prices stay unknown in the results row.
                pass
        trajectory = Trajectory(
            session_id=self.session_id,
            agent=Agent(name=self.name(), version=self.version(), model_name=self.model_name, tool_definitions=[]),
            steps=[Step(step_id=1, source="user", message=instruction),
                   Step(step_id=2, source="agent", message=message.content or "", model_name=self.model_name,
                        reasoning_effort=options.reasoning_effort, llm_call_count=1,
                        reasoning_content=getattr(message, "reasoning_content", None),
                        extra={"stop_reason": stop_reason},
                        metrics=Metrics(prompt_tokens=context.n_input_tokens, cached_tokens=context.n_cache_tokens,
                                        completion_tokens=context.n_output_tokens, cost_usd=context.cost_usd))],
        )
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "trajectory.json").write_text(trajectory.model_dump_json(exclude_none=True, indent=2) + "\n")
