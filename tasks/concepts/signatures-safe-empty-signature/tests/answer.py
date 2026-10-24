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
    sentences = re.split(r"[.!?](?:\s|$)|\n+", text)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()][:2]
    opening = " ".join(sentences)
    if not sentences:
        return False
    first = sentences[0]
    approval = (
        r"\b(signedmessages|signmessage|signmessagelib)\b"
        r"|\bpre[\s-]?(approved|approval|signed)\b"
        r"|\b(previously|already|beforehand|earlier|prior|previous|before|advance)\b"
        r".*\b(signed|approved|approval|signing)\b"
        r"|\b(signed|approved|approval|signing)\b"
        r".*\b(previously|already|beforehand|earlier|prior|previous|before|advance)\b"
        r"|\bon[\s-]?chain\b.*\b(signed|approved|approval|signing)\b"
        r"|\b(signed|approved|approval|signing)\b.*\bon[\s-]?chain\b"
        r"|\bsafe\b.*\b(has|had|have)\s+(?:already\s+)?(signed|approved)\b"
    )
    answer = first if re.search(approval, first) else opening
    return bool(
        not re.search(
            r"\b(uninitialized|never|always|unapproved|unsigned)\b|==\s*0\b"
            r"|\b(not|no|without)\s+(?:been\s+)?(?:signed|approved|approval|signedmessages)\b",
            answer,
        )
        and not (
            re.search(r"\b(approvedhashes|approvehash)\b", first)
            and not re.search(r"\b(signedmessages|signmessage|signmessagelib)\b", first)
        )
        and re.search(approval, opening)
    )


rk.final_answer(accepts, name="safe_message_approved")
