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
    opening = re.match(r"(?:the\s+)?(?:dapp(?:'s)?|application(?:'s)?)(?:\s+domain)?\b", text)
    conflicting = re.search(
        r"^(?:the\s+)?(?:dapp(?:'s)?|application(?:'s)?)(?:\s+domain)?\s*(?:or|and|/|,)\s*(?:the\s+)?account\b"
        r"|(?:^|[.!?;\n]\s*|\b(?:actually|instead|(?:final\s+)?answer(?:\s+is)?|correction)\s*[:, ]*)"
        r"(?:the\s+)?account(?:'s)?(?:\s+domain)?(?=\s*[,.;:!?]|\s*$)",
        text,
    )
    return opening is not None and conflicting is None


rk.final_answer(accepts, name="dapp_domain")
