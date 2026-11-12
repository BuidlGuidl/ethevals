import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk

rk.final_answer(
    lambda reply: re.match(r"(?:the\s+)?per[\s-]?token\b", re.sub(r"^[\W_]+", "", reply), re.IGNORECASE) is not None,
    name="royalty_after_burn",
)
