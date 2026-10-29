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
    target = r"(?:the\s+)?(?:dapp(?:'s)?|application(?:'s)?)"
    alternative = r"(?:the\s+)?account(?:'s)?(?:\s+domain)?"
    opening = re.match(target + r"\b", text)
    conflicting = re.search(
        r"^" + target + r"\s*(?:or|and|/|,)\s*" + alternative + r"\b"
        r"|(?:^|[.!?;\n]\s*|\b(?:actually|instead|(?:final\s+)?answer(?:\s+is)?|correction)\s*[:, ]*)"
        + alternative + r"(?=\s*[,.;:!?]|\s*$)",
        text,
    )
    return opening is not None and conflicting is None


rk.final_answer(accepts, name="dapp_domain_outside")
