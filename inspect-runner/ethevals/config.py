from pathlib import Path
from typing import Literal

import yaml
from inspect_ai.model import ModelCost, ModelInfo, get_model_info, set_model_info
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class Declaration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def read_yaml(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return value


def parse_file(schema: type[Declaration], path: Path) -> Declaration:
    try:
        return schema.model_validate(read_yaml(path))
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


class ModelConfig(Declaration):
    model: str
    effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
    harness: str
    price_source: str
    prices: Prices


Mode = Literal["vanilla", "internet", "skills"]


class Config(Declaration):
    epochs: int = Field(gt=0)
    time_limit: int = Field(gt=0)
    time_limits: dict[str, int] = Field(default_factory=dict)
    token_limit: int = Field(default=500000, gt=0)
    max_tasks: int = Field(default=4, gt=0)
    max_samples: int = Field(default=4, gt=0)
    grader: str
    search_provider: str | None
    models: dict[str, ModelConfig]

    @model_validator(mode="after")
    def check_grader(self):
        if self.grader not in self.models:
            raise ValueError("grader must name a configured model")
        if any(key not in {"quiz", "build", "act", "scenario"} or value <= 0 for key, value in self.time_limits.items()):
            raise ValueError("time_limits requires eval types and positive seconds")
        return self


def load_config(path: Path | None = None) -> Config:
    return parse_file(Config, path or Path(__file__).with_name("config.yaml"))


def register_prices(config: Config) -> None:
    for item in config.models.values():
        info = get_model_info(item.model) or ModelInfo()
        set_model_info(item.model, info.model_copy(update={"cost": ModelCost(**item.prices.model_dump())}))
