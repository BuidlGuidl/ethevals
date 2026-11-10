import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk

def accepts(reply: str) -> bool:
    reply = re.sub(r'^\s*[*_#`]*(?:(?:short|final)\s+)?answer[*_`]*\s*:[*_`]*\s*', "", reply, flags=re.I)
    return reply.strip(string.whitespace + string.punctuation).endswith("8004")


rk.final_answer(
    accepts,
    name="erc_number",
)
