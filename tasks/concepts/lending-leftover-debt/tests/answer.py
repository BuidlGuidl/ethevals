import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"[*_#`]", "", reply).strip(string.whitespace + string.punctuation).lower()
    opening = re.split(r"(?<=[.!?])\s|\n", text, maxsplit=1)[0]
    return bool(re.search(r"\blast\b", opening) and not re.search(r"\b(?:every|all)\s+(?:the\s+)?lenders?\b", opening))


rk.final_answer(accepts, name="loss_falls_on")
