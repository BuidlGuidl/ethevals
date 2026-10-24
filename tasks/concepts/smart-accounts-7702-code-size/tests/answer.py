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
        r"(?:23|twenty[\s-]three)(?:\s+bytes?)?"
        r"(?!\.\d)(?=$|\s*[.,;:!?\n(\[—-]|\s+(?:is|for|the)\b)", text
    ))


rk.final_answer(accepts, name="delegation_size_23")
