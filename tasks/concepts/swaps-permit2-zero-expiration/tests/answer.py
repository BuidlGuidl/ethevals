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
        r"(?:at\s+)?(?:the\s+)?(?:end of\s+(?:the\s+)?)?"
        r"(?:current|same|this|approval)\s+block\b|"
        r"(?:at\s+)?block\.timestamp\b|"
        r"(?:only\s+)?(?:usable|valid|for)\s+(?:(?:in|for)\s+)?(?:the\s+)?"
        r"(?:current|same|this|approval)\s+block\b", text
    ))


rk.final_answer(accepts, name="expires_at_current_block")
