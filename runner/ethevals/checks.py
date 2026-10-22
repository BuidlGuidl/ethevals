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


class JudgeError(ValueError):
    def __init__(self, reason, rewards, checks):
        super().__init__(reason)
        self.rewards = rewards
        self.checks = checks


def read_details(verifier: Path) -> list[dict]:
    path = verifier / "reward-details.json"
    details = []

    def collect(detail):
        details.append(detail)
        for component in detail.get("components", []):
            collect(component["detail"])

    try:
        for detail in json.loads(path.read_text()).values():
            collect(detail)
        return details
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"{path}: {error}") from error


def read_reward(verifier: Path, *, details: list[dict] | None = None) -> tuple[dict, dict]:
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
    errors = []

    def collect(detail):
        judged = detail.get("kind") in {"llm", "agent", "jev"}
        if judged and detail.get("guard", {}).get("error"):
            errors.append(f"Judge guard: {detail['guard']['error']}")
        for item in detail.get("criteria", []):
            name = item["name"]
            if name in checks:
                raise ValueError(f"Duplicate RewardKit check {name!r}.")
            if item.get("error"):
                if judged:
                    errors.append(f"{name}: {item['error']}")
                    continue
                raise ValueError(f"{name}: {item['error']}")
            if judged and (type(item.get("raw")) not in (bool, int, str)
                           or item["raw"] not in (True, False, 0, 1, "yes", "no")
                           or not isinstance(item.get("reasoning"), str) or not item["reasoning"].strip()):
                errors.append(f"{name}: the judge must answer yes or no and give a reason.")
                continue
            value = item["value"]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name}: criterion value must be a finite number.")
            checks[name] = {"passed": value >= 1, "reason": " ".join(
                (item.get("reasoning") or item.get("description") or name).split())}

    try:
        for detail in details if details is not None else read_details(verifier):
            collect(detail)
        if errors:
            raise JudgeError("; ".join(errors), rewards, checks)
        return rewards, validate_checks(checks)
    except JudgeError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"{details_path}: {error}") from error
