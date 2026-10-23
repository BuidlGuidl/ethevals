import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"[*_#`]", "", reply).strip(string.whitespace + string.punctuation).lower()
    text = re.sub(r"^(?:only|just)\s+", "", text)
    return bool(re.match(r"withdraw(?:ing|al|als)?\b", text))


rk.final_answer(accepts, name="withdraw_without_price")
