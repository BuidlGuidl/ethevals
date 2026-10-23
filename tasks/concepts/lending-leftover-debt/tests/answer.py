import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = reply.lower()
    return bool(re.search(r"\blast\b", text) and not re.search(r"\b(?:every|all)\s+(?:the\s+)?lenders?\b", text))


rk.final_answer(accepts, name="loss_falls_on")
