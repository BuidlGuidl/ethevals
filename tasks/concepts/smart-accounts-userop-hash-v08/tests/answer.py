import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    reply = re.sub(r"(?m)^\s*```[^\n]*\n", "", reply)
    text = re.sub(r"[*_#`]", "", reply).lower()
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "‑": "-", "–": "-"}))
    text = text.strip(string.whitespace + string.punctuation.replace("-", "").replace("+", ""))
    text = re.sub(r"^short\s+answer\s*:\s*", "", text)
    return bool(
        re.match(r"(?:(?:as(?:\s+an?)?|it's|it is|using|via|by|an?)\s+)?eip[\s-]?712\b", text)
        and re.search(r"\bhash\w*\b|\btyped[\s-]+data\b", text)
        or re.match(r"keccak256\s*\(\s*0x1901\b", text)
        and re.search(r"\bdomainseparator\b|\bdomain[\s-]+separator\b", text)
    )


rk.final_answer(accepts, name="userop_eip712_hash")
