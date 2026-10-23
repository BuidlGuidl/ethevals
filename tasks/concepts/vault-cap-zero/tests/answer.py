import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = reply.strip(string.whitespace + string.punctuation).lower()
    return bool(re.match(r"yes\b", text) and re.search(r"on\s+(?:the\s+vault['’]s\s+)?behalf|for\s+the\s+vault|(?:as|named\s+as)\s+(?:the\s+)?receiver|donat", text))


rk.final_answer(accepts, name="supply_on_behalf")
