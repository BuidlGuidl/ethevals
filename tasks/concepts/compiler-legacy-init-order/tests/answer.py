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
    opening = re.match(r"(?:the\s+)?zero(?:\s+address)?\b|address\(0\)(?!\w)|0x0+(?!\w)", text)
    conflicting = re.search(
        r"^(?:(?:the\s+)?zero(?:\s+address)?|address\(0\)|0x0+)\s*(?:or|and|/)\s*alice\b"
        r"|^(?:(?:the\s+)?zero(?:\s+address)?|address\(0\)|0x0+)\s*,\s*"
        r"alice(?:'s)?(?:\s+address)?(?=\s*[,.;:!?]|\s*$)"
        r"|(?:^|[.!?;\n]\s*|\b(?:actually|instead|(?:final\s+)?answer(?:\s+is)?|correction)\s*[:, ]*)"
        r"alice(?:'s)?(?:\s+address)?(?=\s*[,.;:!?]|\s*$)",
        text,
    )
    return opening is not None and conflicting is None


rk.final_answer(accepts, name="zero_fee_recipient")
