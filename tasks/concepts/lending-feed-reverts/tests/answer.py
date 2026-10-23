import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = reply.strip(string.whitespace + string.punctuation).lower()
    return bool(re.match(r"withdraw(?:ing|al|als)?\b", text))


rk.final_answer(accepts, name="withdraw_without_price")
