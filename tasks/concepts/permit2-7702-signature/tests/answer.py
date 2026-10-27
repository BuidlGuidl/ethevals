import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk

rk.final_answer(
    lambda reply: re.match(r"(?:ERC-?1271|EIP-1271)\b", re.sub(r"^[\W_]+", "", reply), re.IGNORECASE) is not None,
    name="signature_check",
)
