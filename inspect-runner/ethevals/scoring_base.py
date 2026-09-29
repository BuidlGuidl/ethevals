"""Check scores and the common scoring failure boundary."""
from inspect_ai.event import SampleLimitEvent
from inspect_ai.log import transcript
from inspect_ai.scorer import Score


def checks_score(checks):
    return Score(value={name: "C" if check["passed"] else "I" for name, check in checks.items()},
                 metadata={"reasons": {name: " ".join(check["reason"].split()) for name, check in checks.items()}})


class SubmissionFailed(Exception):
    pass


def scoring_boundary(name, score):
    async def checked(state, target):
        limit = next((event for event in reversed(transcript().events) if isinstance(event, SampleLimitEvent)), None)
        try:
            if limit:
                if limit.type == "operator" or (limit.type == "time" and
                        limit.working_start < state.metadata["working_limit_seconds"]):
                    raise RuntimeError(f"Epoch stopped by {limit.type} before its working limit. {limit.message}")
                raise SubmissionFailed(f"Epoch reached {limit.type} limit {limit.limit}. {limit.message}")
            return await score(state, target)
        except SubmissionFailed as error:
            reason = str(error)
        return checks_score({name: {"passed": False, "reason": reason}})
    return checked
