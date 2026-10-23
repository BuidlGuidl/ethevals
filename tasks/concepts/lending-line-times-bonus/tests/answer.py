import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"[*_#`]", "", reply).lower()
    number = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text)
    if number:
        return float(number.group()) == 0
    return bool(re.search(r"\b(?:zero|none|already)\b", text))


rk.final_answer(accepts, name="no_price_margin")
