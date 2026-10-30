import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def clean(reply: str) -> str:
    text = re.sub(r"(?m)^\s*```[^\n]*\n", "", reply)
    text = re.sub(r"[*_#`]", "", text).lower()
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "“": "\"", "”": "\"", "‑": "-", "–": "-"}))
    text = text.strip(string.whitespace + string.punctuation.replace("-", "").replace("+", ""))
    return re.sub(r"^(?:short\s+answer|answer)\s*:\s*", "", text)


def accepts(reply: str) -> bool:
    text = clean(reply)
    address = re.search(r"\b0x[0-9a-f]+\b", text)
    return bool(re.match(r"yes\b", text) and address and int(address.group(), 16) == 0x0000F90827F1C53a10cb7A02335B175320002935)


rk.final_answer(accepts, name="history_contract_address")
