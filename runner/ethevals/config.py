from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError


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
