import re
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk

TARGET = "0x" + "f" * 39 + "e"


def accepts(reply: str) -> bool:
    addresses = [a.casefold() for a in re.findall(r"0x[0-9a-fA-F]{40}(?![0-9a-fA-F])", reply)]
    return bool(addresses) and addresses[0] == TARGET


rk.final_answer(accepts, name="system_transfer_log_address")
