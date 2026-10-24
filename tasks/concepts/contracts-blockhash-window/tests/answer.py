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
    return bool(
        re.match(r"no\b", text)
        and re.search(r"\b256[\s-]+block(?:s|\b)", text)
        and not re.search(r"\b8,?192\b", text)
    )


rk.final_answer(accepts, name="blockhash_keeps_256_window")
