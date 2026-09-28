from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class Declaration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def read_yaml(path: Path, data: bytes | None = None) -> dict:
    try:
        value = yaml.safe_load(path.read_text() if data is None else data)
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return value


def parse_file(schema: type[Declaration], path: Path, data: bytes | None = None) -> Declaration:
    try:
        return schema.model_validate(read_yaml(path, data))
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
            for item in error.errors(include_input=False)
        )
        raise ValueError(f"{path}: {details}") from error


class Prices(Declaration):
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    input_cache_read: float = Field(ge=0)
    input_cache_write: float = Field(ge=0)


class ModelSettings(Declaration):
    model: str
    effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
    price_source: str
    prices: Prices


class ModelConfig(ModelSettings):
    harness: str | None
    agent_model_config: str | None = None


class GraderConfig(ModelSettings):
    max_tokens: int = Field(gt=0)


Mode = Literal["vanilla", "internet", "skills"]


class Config(Declaration):
    epochs: int = Field(gt=0)
    time_limit: int = Field(gt=0)
    time_limits: dict[str, int] = Field(default_factory=dict)
    cost_limit: float = Field(gt=0)
    max_attempts: int = Field(gt=0)
    max_tasks: int = Field(default=4, gt=0)
    max_samples: int = Field(default=4, gt=0)
    grader: GraderConfig
    search_provider: str | None
    search_limit: int = Field(default=20, gt=0)
    search_price_usd: float = Field(default=0.05, gt=0, allow_inf_nan=False)
    models: dict[str, ModelConfig]

    @model_validator(mode="after")
    def check_grader(self):
        from .agents import AGENTS
        if self.search_provider not in {None, "https://mcp.exa.ai/mcp"}:
            raise ValueError("search_provider must be the key-free Exa endpoint or null")
        if any(key not in {"quiz", "build", "act", "scenario"} or value <= 0 for key, value in self.time_limits.items()):
            raise ValueError("time_limits requires eval types and positive seconds")
        for key, model in self.models.items():
            if model.harness is not None and model.harness not in AGENTS:
                raise ValueError(f"models.{key}.harness: unknown harness {model.harness!r}")
        prices = {}
        for item in [self.grader, *self.models.values()]:
            if item.model in prices and prices[item.model] != item.prices:
                raise ValueError(f"Conflicting prices for model {item.model}")
            prices[item.model] = item.prices
        return self


def load_config(path: Path | None = None) -> Config:
    return parse_file(Config, path or Path(__file__).with_name("config.yaml"))
