"""Read RewardKit output and validate displayed checks."""
import json
import math
from pathlib import Path


def validate_checks(checks: object) -> dict:
    if not isinstance(checks, dict) or not checks or any(
        not isinstance(name, str) or not name.strip() or not isinstance(check, dict)
        or type(check.get("passed")) is not bool or not isinstance(check.get("reason"), str)
        or not check["reason"].strip() or len(check["reason"].splitlines()) != 1
        for name, check in checks.items()
    ):
        raise ValueError("Each check needs a name, boolean passed, and one-line reason.")
    return checks


def read_reward(verifier: Path) -> tuple[dict, dict]:
    rewards_path = verifier / "reward.json"
    details_path = verifier / "reward-details.json"
    try:
        rewards = json.loads(rewards_path.read_text())
        if (not isinstance(rewards, dict) or "reward" not in rewards
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in rewards.values())):
            raise ValueError("RewardKit must write numeric rewards including reward.")
    except (OSError, ValueError) as error:
        raise ValueError(f"{rewards_path}: {error}") from error
    checks = {}

    def collect(detail):
        for item in detail.get("criteria", []):
            name = item["name"]
            if name in checks:
                raise ValueError(f"Duplicate RewardKit check {name!r}.")
            if item.get("error"):
                raise ValueError(f"{name}: {item['error']}")
            value = item["value"]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name}: criterion value must be a finite number.")
            checks[name] = {"passed": value >= 1, "reason": " ".join(
                (item.get("reasoning") or item.get("description") or name).split())}
        for component in detail.get("components", []):
            collect(component["detail"])

    try:
        details = json.loads(details_path.read_text())
        for detail in details.values():
            collect(detail)
        return rewards, validate_checks(checks)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"{details_path}: {error}") from error
