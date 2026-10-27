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
        re.match(r"yes\b", text)
        and re.search(
            r"\b(?:erc|eip)[\s-]*1271\b|\bisvalidsignature\b|"
            r"\b(?:smart[\s-]+)?contract signatures?\b|\bsignaturechecker\b|\bv2\.2\b", text
        )
    )


rk.final_answer(accepts, name="usdc_permit_erc1271")
