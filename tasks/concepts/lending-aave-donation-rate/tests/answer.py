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
        re.match(r"no\b", text)
        and re.search(
            r"\bvirtual(?:underlyingbalance)?\b|\binternally[\s-]+tracked\b|"
            r"\binternal accounting\b|\btracked internally\b|\bits own accounting\b|"
            r"\b(?:doesn't|does not) read (?:the )?(?:token )?balance(?:of)?\b|"
            r"\bignores (?:the )?token balance\b", text
        )
    )


rk.final_answer(accepts, name="donation_uses_virtual_balance")
