import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = reply.lower()
    return bool(re.search(r"\b(?:high|overstated|overestimat(?:e|ed))\b", text) and not re.search(r"\b(?:low|understated|underestimat(?:e|ed))\b", text))


rk.final_answer(accepts, name="lender_apy_too_high")
