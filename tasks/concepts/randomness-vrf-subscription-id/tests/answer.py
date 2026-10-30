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


rk.final_answer(
    lambda reply: re.match(r"no\b", clean(reply)) is not None,
    name="subscription_id_does_not_fit",
)
