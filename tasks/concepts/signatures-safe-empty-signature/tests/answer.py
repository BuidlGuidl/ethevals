import re
import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk


def accepts(reply: str) -> bool:
    text = re.sub(r"(?m)^\s*```[^\n]*\n", "", reply)
    text = re.sub(r"[*_#`]", "", text).strip(string.whitespace + string.punctuation).lower()
    text = re.sub(r"^short\s+answer\s*:\s*", "", text)
    opening = re.split(r"[.\n](?:\s|$)", text, maxsplit=1)[0]
    return bool(
        not re.search(r"\b(uninitialized|never|always)\b|==\s*0\b|\bnot\s+approved\b", opening)
        and re.search(r"\b(message|safemessage|hash|signedmessages|signmessage|signmessagelib)\b", opening)
        and re.search(
            r"\b(signedmessages|signmessage|signmessagelib)\b"
            r"|\b(approved|approval)[\s-]+on[\s-]?chain\b"
            r"|\bon[\s-]?chain[\s-]+(message[\s-]+)?(approved|approval)\b"
            r"|\bpre[\s-]?(approved|approval)\b",
            opening,
        )
    )


rk.final_answer(accepts, name="safe_message_approved")
