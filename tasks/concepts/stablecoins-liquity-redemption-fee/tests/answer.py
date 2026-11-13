import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"[*_#`]", "", reply).lower()
    # The first of the four offered parties named in the reply is the choice.
    match = re.search(r"\b(redeemer|stakers?|protocol|borrowers?|trove)\b", text)
    return match is not None and match.group(1) in ("borrower", "borrowers", "trove")


rk.final_answer(accepts, name="redemption_fee_recipient")
