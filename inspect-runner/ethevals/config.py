from pathlib import Path
from typing import Annotated, Literal

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


class ModelConfig(ModelSettings):
    harness: str | None
    agent_model_config: str | None = None


class GraderConfig(ModelSettings):
    max_tokens: int = Field(gt=0)


Mode = Literal["vanilla", "internet", "skills"]


def uses_sandbox(mode: Mode) -> bool:
    return mode != "vanilla"


class Config(Declaration):
    epochs: int = Field(gt=0)
    time_limits: dict[Literal["quiz", "build", "act"], Annotated[int, Field(gt=0)]]
    cost_limit: float = Field(gt=0)
    max_attempts: int = Field(gt=0)
    concurrency: int = Field(gt=0)
    grader: GraderConfig
    search: bool
    search_limit: int = Field(gt=0)
    search_price_usd: float = Field(gt=0, allow_inf_nan=False)
    agents: dict[str, ModelConfig]
    prices: dict[str, Prices]

    @model_validator(mode="after")
    def check_grader(self):
        from .agents import HARNESSES
        if self.time_limits.keys() != {"quiz", "build", "act"}:
            raise ValueError("time_limits requires quiz, build, and act")
        for key, model in self.agents.items():
            if model.harness is not None and model.harness not in HARNESSES:
                raise ValueError(f"agents.{key}.harness: unknown harness {model.harness!r}")
        for item in [self.grader, *self.agents.values()]:
            if item.model not in self.prices:
                raise ValueError(f"prices.{item.model}: missing model prices")
        return self


def load_config(path: Path | None = None) -> Config:
    return parse_file(Config, path or Path(__file__).with_name("config.yaml"))
