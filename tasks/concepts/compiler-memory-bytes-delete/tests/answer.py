import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"(?m)^\s*```[^\n]*\n", "", reply)
    text = re.sub(r"[*_#`]", "", text).casefold()
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "–": "-", "—": "-"}))
    text = text.strip().lstrip("\"'([ ").strip()
    target = r"(?:(?:the\s+)?zero(?:\s+address)?|address\(0\)|0x0+)"
    alternative = r"alice(?:'s)?(?:\s+address)?"
    opening = re.match(r"(?:the\s+)?zero(?:\s+address)?\b|address\(0\)(?!\w)|0x0+(?!\w)", text)
    conflicting = re.search(
        r"^" + target + r"\s*[,;]?\s*(?:or|and|/)\s*" + alternative + r"\b"
        r"|^" + target + r"\s*[,;]\s*" + alternative + r"(?=\s*[,.;:!?]|\s*$)"
        r"|^" + target + r"\s*\(\s*(?:or\s+)?" + alternative + r"\b"
        r"|(?:^|[.!?\n]\s*)(?:the\s+)?(?:final\s+)?answer(?:\s+is)?\s*[:,]?\s*" + alternative + r"\b"
        r"|\b(?:actually|instead|correction)\s*[:,]?\s*" + alternative + r"\b"
        r"|(?:^|[.!?\n]\s*)" + alternative + r"(?=\s*[.!?]|\s*$)",
        text,
    )
    return opening is not None and conflicting is None


rk.final_answer(accepts, name="zero_payload_recipient")
