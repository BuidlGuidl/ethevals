import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk

def accepts(reply: str) -> bool:
    reply = re.sub(r'^\s*[*_#`]*(?:(?:short|final)\s+)?answer[*_`]*\s*:[*_`]*\s*', "", reply, flags=re.I)
    text = re.sub(r"[*_#`]", "", reply).casefold().strip().lstrip("\"'([ ").strip()
    target = r"no"
    alternative = r"yes"
    opening = re.match(target + r"\b", text, re.IGNORECASE)
    conflicting = re.search(
        r"^" + target + r"\s*[,;]?\s*(?:or|and|/)\s*(?:(?:perhaps|maybe)\s+)?" + alternative + r"\b"
        r"|^" + target + r"\s*[,;]\s*" + alternative + r"(?=\s*[,.;:!?]|\s*$)"
        r"|^" + target + r"\s*\(\s*(?:or\s+)?" + alternative + r"\b"
        r"|(?:^|[.!?\n]\s*)(?:the\s+)?(?:final\s+)?answer(?:\s+is)?\s*[:,]?\s*" + alternative + r"\b"
        r"|\b(?:actually|instead|correction)\s*[:,]?\s*" + alternative + r"\b"
        r"|(?:^|[.!?\n]\s*)" + alternative + r"(?=\s*[.!?]|\s*$)", text, re.IGNORECASE,
    )
    return opening is not None and conflicting is None


rk.final_answer(
    accepts,
    name="zero_expiration",
)
