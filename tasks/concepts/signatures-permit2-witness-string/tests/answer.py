import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


TARGET = "VaultDeposit witness)TokenPermissions(address token,uint256 amount)VaultDeposit(address receiver)"


def accepts(reply: str) -> bool:
    reply = re.sub(r'^\s*[*_#`]*(?:(?:short|final)\s+)?answer[*_`]*\s*:[*_`]*\s*', "", reply, flags=re.I)
    text = re.sub(r"(?m)^\s*```[^\n]*\n", "", reply).strip()
    text = re.sub(r"^\*?\*?Short answer:\*?\*?\s*", "", text, flags=re.I)
    text = text.lstrip("`\"'")
    return bool(re.match(re.escape(TARGET) + r"(?=$|[\r\n`\"']|[.;](?:\s|$))", text))


rk.final_answer(accepts, name="witness_type_string")
