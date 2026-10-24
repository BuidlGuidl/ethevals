import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    reply = re.sub(r"(?m)^\s*```[^\n]*\n", "", reply)
    text = re.sub(r"[*_#`]", "", reply).strip(string.whitespace + string.punctuation).lower()
    text = re.sub(r"^short\s+answer\s*:\s*", "", text)
    return bool(
        re.match(r"no\b", text)
        and re.search(
            r"\b(?:wrapped|wrapping|wrapper|deposited|deposits|opted)\b"
            r"|\bvote[\s-]+token(?:'s)?\s+(?:total\s+)?supply\b",
            text,
        )
    )


rk.final_answer(accepts, name="wrapped_supply_quorum")
