import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"[*_#`]", "", reply).lower()
    first_sentence = re.split(r"(?<=[.!?])\s|\n", text.strip(), maxsplit=1)[0]
    return re.search(r"\bzombie\b", first_sentence) is not None


rk.final_answer(accepts, name="zombie_status")
