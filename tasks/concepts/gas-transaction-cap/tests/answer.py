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
    text = clean(reply).replace(",", "").replace("_", "").replace(" ", "")
    return "16777216" in text or "2^24" in text or "2**24" in text


rk.final_answer(accepts, name="transaction_gas_cap")
