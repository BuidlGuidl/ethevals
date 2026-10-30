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
    opening = re.match(r"0(?![\w]|\.\d)", text)
    conflicting = re.search(
        r"^0\s*(?:or|and|/|,)\s*[+-]?\d"
        r"|\b(?:actually|instead|(?:final\s+)?answer(?:\s+is)?|correction)\s*[:, ]*"
        r"(?!0(?![\w]|\.\d))[+-]?\d+"
        r"|(?:\.\s+|\n\s*)(?!0\b)[+-]?\d+\s*\.?\s*$",
        text,
    )
    return opening is not None and conflicting is None


rk.final_answer(accepts, name="shifted_balance_reads_zero")
