"""Check scores and the common scoring failure boundary."""
from inspect_ai.event import SampleLimitEvent
from inspect_ai.log import transcript
from inspect_ai.scorer import Score


def checks_score(checks, *, answer=None):
    reasons = {name: " ".join(check["reason"].split()) for name, check in checks.items()}
    return Score(value={name: "C" if check["passed"] else "I" for name, check in checks.items()},
                 answer=answer, explanation="\n".join(f"{name}: {reason}" for name, reason in reasons.items()),
                 metadata={"reasons": reasons})


class SubmissionFailed(Exception):
    pass


def epoch_limit():
    return next((event for event in reversed(transcript().events) if isinstance(event, SampleLimitEvent)), None)


def scoring_boundary(name, score, *, freeze=False, evaluation=None):
    async def checked(state, target):
        limit = epoch_limit()
        try:
            if limit and limit.type != "time":
                if limit.type == "operator":
                    raise RuntimeError(f"Epoch stopped by operator. {limit.message}")
                if name is None:
                    return None
                raise SubmissionFailed(f"Epoch reached {limit.type} limit {limit.limit}. {limit.message}")
            if freeze and (evaluation.declaration.chain or "tests" in evaluation.scorer_kinds):
                from .sandboxes import stop_agent
                from .chain_setup import capture_chain
                await stop_agent()
                if evaluation.declaration.chain:
                    await capture_chain()
            return await score(state, target)
        except SubmissionFailed as error:
            reason = str(error)
        return checks_score({name: {"passed": False, "reason": reason}})
    return checked
