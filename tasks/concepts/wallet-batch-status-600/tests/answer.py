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
    first = re.split(r"[.!?\n]", text, maxsplit=1)[0]
    if re.search(
        r"\b(?:rejected|undefined|out[- ]of[- ]spec|pending|confirmed)\b|"
        r"\b(?:whole|entire|full|all)\b.*\b(?:failed|failure|reverted)\b", first
    ):
        return False
    return bool(re.search(
        r"\bpartial(?:ly)?\b|"
        r"\bmixed\b.*\b(?:execution|outcomes?)\b|\b(?:execution|outcomes?)\b.*\bmixed\b|"
        r"\bsome calls (?:reverted|failed)\b.*\bothers (?:succeeded|went through)\b", first
    ))


rk.final_answer(accepts, name="partial_onchain_revert")
