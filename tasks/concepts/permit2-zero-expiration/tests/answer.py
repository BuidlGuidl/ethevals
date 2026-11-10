import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk

def accepts(reply: str) -> bool:
    reply = re.sub(r'^\s*[*_#`]*(?:(?:short|final)\s+)?answer[*_`]*\s*:[*_`]*\s*', "", reply, flags=re.I)
    return re.match(r"no\b", re.sub(r"^[\W_]+", "", reply), re.IGNORECASE) is not None


rk.final_answer(
    accepts,
    name="zero_expiration",
)
