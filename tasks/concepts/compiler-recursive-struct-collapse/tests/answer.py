import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    reply = re.sub(r'^\s*[*_#`]*(?:(?:short|final)\s+)?answer[*_`]*\s*:[*_`]*\s*', "", reply, flags=re.I)
    text = re.sub(r"[*_#`]", "", reply).casefold().replace(",", "")
    numbers = re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.]*\d)", text)
    revised = re.search(r"\b(?:final\s+answer|actually|instead|correction)\b\s*(?:is)?\s*[:,]?\s*(\d+)", text)
    return bool(numbers) and numbers[0] == "40" and (revised is None or revised.group(1) == "40")


rk.final_answer(accepts, name="lost_child_budget")
