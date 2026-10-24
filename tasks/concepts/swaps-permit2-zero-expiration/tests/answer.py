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
    first_sentence = re.split(r"[.!?](?:\s|$)", text, maxsplit=1)[0]
    return bool(
        re.search(
            r"\bblock\.timestamp\b|\b(?:current|same|this|that|approval)\s+block\b|"
            r"\bend of (?:the )?block\b", first_sentence
        )
        and not re.search(
            r"\bunusable\b|\bnever works\b|\balready (?:expired|in the past)\b|"
            r"\bdead on arrival\b|\bnever expires\b", text
        )
    )


rk.final_answer(accepts, name="expires_at_current_block")
