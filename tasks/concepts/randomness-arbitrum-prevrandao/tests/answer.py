import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def clean(reply: str) -> str:
    text = re.sub(r"(?m)^\s*```[^\n]*\n", "", reply)
    text = re.sub(r"[*_#`]", "", text).lower()
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "“": "\"", "”": "\"", "‑": "-", "–": "-"}))
    text = text.strip(string.whitespace + string.punctuation.replace("-", "").replace("+", ""))
    return re.sub(r"^(?:short\s+answer|answer)\s*:\s*", "", text)


def accepts(reply: str) -> bool:
    number = re.search(r"\b(0x[0-9a-f]+|\d+)\b", clean(reply))
    return bool(number) and int(number.group(), 0) == 1


rk.final_answer(accepts, name="prevrandao_is_one")
