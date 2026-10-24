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
    parts = re.split(r"\b(supported|ready)\b", text, maxsplit=2)
    if len(parts) != 5 or parts[1] == parts[3]:
        return False
    states = {parts[1]: parts[2], parts[3]: parts[4]}
    supported, ready = states["supported"], states["ready"]
    return bool(
        re.search(r"\batomic\w*\b", supported)
        and not re.search(r"\bnot\b|\bcannot\b|\bupgrad\w*\b|\bsetup\b|\brequires?\b", supported)
        and re.search(r"\bupgrad\w*\b", ready)
    )


rk.final_answer(accepts, name="supported_now_ready_upgrade")
