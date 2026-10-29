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
    target = r"(?:the\s+)?(?:dapp|app|application)(?:'s)?(?:\s+domain(?:\s+separator)?)?"
    alternative = r"(?:the\s+)?account(?:'s)?(?:\s+domain(?:\s+separator)?)?"
    opening = re.match(r"(?:the\s+)?(?:dapp|app|application)(?:'s)?\b", text)
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


rk.final_answer(accepts, name="dapp_domain_outside")
