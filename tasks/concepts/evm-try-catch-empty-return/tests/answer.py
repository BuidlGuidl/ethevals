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
    opening = re.match(r"no\b", text)
    conflicting = re.search(
        r"\b(?:no\s*(?:/|or|and)\s*yes|yes\s*(?:/|or|and)\s*no)\b"
        r"|^no\s*[,;]\s*(?:or|and|/)\s*yes\b"
        r"|^no\s*[,;]\s*yes\b(?=\s*[,.;:!?]|\s*$)"
        r"|^no\s*\(\s*(?:or\s+)?yes\b"
        r"|(?:^|[.!?\n]\s*)(?:the\s+)?(?:final\s+)?answer(?:\s+is)?\s*[:,]?\s*yes\b"
        r"|\b(?:actually|instead|correction)\s*[:,]?\s*yes\b"
        r"|(?:^|[.!?\n]\s*)yes\b(?=\s*[.!?]|\s*$)",
        text,
    )
    return opening is not None and conflicting is None


rk.final_answer(accepts, name="eoa_hook_reverts_liquidation")
