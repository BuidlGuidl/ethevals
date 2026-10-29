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
    opening = re.match(r"yes\b", text)
    conflicting = re.search(
        r"\b(?:yes\s*(?:/|or|and)\s*no|no\s*(?:/|or|and)\s*yes)\b"
        r"|\b(?:yes\s*[,;]\s*no|no\s*[,;]\s*yes)\b(?=\s*[,.;:!?]|\s*$)"
        r"|(?:^|[.!?;\n]\s*|\b(?:actually|instead|(?:final\s+)?answer(?:\s+is)?|correction)\s*[:, ]*)"
        r"no\b(?=\s*[,.;:!?]|\s*$)",
        text,
    )
    return opening is not None and conflicting is None


rk.final_answer(accepts, name="warm_safe_receives_refund")
