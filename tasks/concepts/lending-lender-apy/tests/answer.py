import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"[*_#`]", "", reply).strip(string.whitespace + string.punctuation).lower()
    opening = re.split(r"(?<=[.!?])\s|\n", text, maxsplit=1)[0]
    return bool(re.search(r"\b(?:high|overstated|overestimat(?:e|ed))\b", opening) and not re.search(r"\b(?:low|understated|underestimat(?:e|ed))\b", opening))


rk.final_answer(accepts, name="lender_apy_too_high")
