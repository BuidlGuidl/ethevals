import string
import sys

sys.path.insert(0, "/opt")
import target_checks
import rewardkit as rk

rk.final_answer(
    lambda reply: reply.strip(string.whitespace + string.punctuation).endswith("8004"),
    name="erc_number",
)
