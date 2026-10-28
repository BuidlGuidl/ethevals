"""Load job settings and check their declared credentials before Harbor starts."""
from importlib.metadata import version
import json
import os
from pathlib import Path
from typing import Any, Literal

from harbor.utils.env import get_required_host_vars, resolve_env_vars
from harbor.models.job.config import RetryConfig
from pydantic import Field, model_validator

from .config import Declaration, parse_file


class JudgeSettings(Declaration):
    model: str = "anthropic/claude-opus-5-5"
    effort: Literal["low", "medium", "high"] = "high"
    cost_limit_usd: float = Field(default=2.0, ge=0, allow_inf_nan=False)
    paid_by: Literal["api_key", "free"] = "api_key"
    key_env: Literal["ANTHROPIC_API_KEY"] = "ANTHROPIC_API_KEY"


def check_judge_key(settings: JudgeSettings) -> None:
    if settings.paid_by == "free":
        return
    key = os.environ.get(settings.key_env, "")
    if not key.strip() or key.startswith("sk-ant-oat"):
        raise ValueError(f"The judge requires {settings.key_env} and cannot use a plan token.")


class ModelSettings(Declaration):
    name: str
    effort: str | None = None
    kwargs: dict[str, Any] = Field(default_factory=dict)


class FileCredential(Declaration):
    path: str
    policy: Literal["plan_tokens"]


class AgentSettings(Declaration):
    name: str
    # Load a different class while results keep `name`, e.g. a Harbor agent with an ETH Evals fix.
    import_path: str | None = None
    version: str = Field(min_length=1, pattern=r"^\d+\.\d+\.\d+[^\s]*$")
    model: str
    paid_by: Literal["plan", "api_key", "free"]
    cost_limit_usd: float = Field(ge=0, allow_inf_nan=False)
    modes: list[Literal["vanilla", "internet", "skills"]] = Field(default_factory=lambda: ["internet"])
    kwargs: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    required_env: list[str] = Field(default_factory=list)
    required_files: list[FileCredential] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_plan_credential(self):
        if self.paid_by == "plan" and not (self.required_env or self.required_files):
            raise ValueError("A plan entry must declare a credential requirement")
        return self


class HubSettings(Declaration):
    org: str = Field(min_length=1)
    key_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class JobSettings(Declaration):
    harbor_version: str
    n_attempts: int = Field(default=3, gt=0)
    retry: RetryConfig = Field(default_factory=lambda: RetryConfig(max_retries=1))
    modes: list[Literal["vanilla", "internet", "skills"]]
    models: dict[str, ModelSettings]
    agents: dict[str, AgentSettings]
    judge: JudgeSettings = Field(default_factory=JudgeSettings)
    hub: HubSettings | None = None

    @model_validator(mode="after")
    def check_references(self):
        for key, agent in self.agents.items():
            if agent.model not in self.models:
                raise ValueError(f"agents.{key}.model: unknown model {agent.model!r}")
        for label, entries in (("agents", self.agents), ("models", self.models)):
            for key, entry in entries.items():
                if {"version", "model_name", "reasoning_effort"} & entry.kwargs.keys():
                    raise ValueError(f"{label}.{key}: set version, model, and effort outside kwargs")
                if "max_budget_usd" in entry.kwargs:
                    raise ValueError(f"{label}.{key}: use cost_limit_usd instead of kwargs.max_budget_usd")
        return self

    def credential_names(self) -> set[str]:
        return {self.judge.key_env} | ({self.hub.key_env} if self.hub else set()) | {name for agent in self.agents.values()
                                      for name in [*agent.required_env, *agent.env]}


def load_job(path: Path | None = None) -> JobSettings:
    config = parse_file(JobSettings, path or Path(__file__).with_name("job.yaml"))
    if config.harbor_version != version("harbor"):
        raise ValueError(f"Job requires Harbor {config.harbor_version}; installed version is {version('harbor')}")
    return config


def check_credentials(agent: AgentSettings, key: str) -> None:
    environment = {**os.environ, **resolve_env_vars(agent.env)}
    for variable in agent.required_env:
        if not environment.get(variable, "").strip():
            raise ValueError(f"{key}: missing {variable}")
    for credential in agent.required_files:
        filename = credential.path
        for variable, default in get_required_host_vars({"path": filename}):
            filename = environment.get(variable) or default
            if filename is None:
                raise ValueError(f"{key}: missing {variable}")
        # Match Harbor's default credential directory without changing HOME.
        path = Path.home() / filename[2:] if filename.startswith("~/") else Path(filename)
        if not path.is_file():
            raise ValueError(f"{key}: missing credential file {path}")
        try:
            parsed = json.loads(path.read_text())
        except (ValueError, OSError) as error:
            raise ValueError(f"{key}: {path}: credential must contain plan tokens") from error
        if credential.policy == "plan_tokens" and (
            not isinstance(parsed, dict) or parsed.get("auth_mode") != "chatgpt"
            or not isinstance(parsed.get("tokens"), dict)
            or not isinstance(parsed["tokens"].get("access_token"), str)
            or not parsed["tokens"]["access_token"].strip()
        ):
            raise ValueError(f"{key}: {path}: credential must contain ChatGPT plan tokens with auth_mode=chatgpt")
