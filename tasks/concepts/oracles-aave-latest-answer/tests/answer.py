import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"[*_#`]", "", reply).strip()
    first = text.split()[0] if text.split() else ""
    first = first.strip(string.punctuation + "()").lower()
    return first.endswith("latestanswer")


rk.final_answer(accepts, name="aave_oracle_call")
