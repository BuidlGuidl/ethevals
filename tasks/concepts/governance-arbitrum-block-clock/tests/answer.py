import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    reply = re.sub(r"(?m)^\s*```[^\n]*\n", "", reply)
    text = re.sub(r"[*_#`]", "", reply).lower()
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "‑": "-", "–": "-"}))
    text = text.strip(string.whitespace + string.punctuation.replace("-", "").replace("+", ""))
    text = re.sub(r"^short\s+answer\s*:\s*", "", text)
    return bool(re.match(
        r"(?:(?:about|approximately|roughly|around)\s+|~\s*)?"
        r"(?:7\s+days?|seven\s+days?|(?:1|one|a)\s+week|168\s+hours?|"
        r"604,?800\s+(?:seconds?|s)\b)\b", text
    ))


rk.final_answer(accepts, name="l1_clock_seven_days")
