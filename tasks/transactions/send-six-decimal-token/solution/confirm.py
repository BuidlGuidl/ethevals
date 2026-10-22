import json
from pathlib import Path
import subprocess

chain = json.loads(Path("/workspace/chain_context.json").read_text())
command = ["cast", "call", chain["token"], "balanceOf(address)(uint256)", chain["recipient"],
           "--rpc-url", chain["rpcUrl"]]
balance = subprocess.check_output(command, text=True).strip()
assert int(balance.split()[0]) == 12_500_000, balance
trajectory = {
    "schema_version": "ATIF-v1.7", "session_id": "solution",
    "agent": {"name": "oracle", "version": "1.0.0"},
    "steps": [
        {"step_id": 1, "source": "agent", "message": "Read the recipient's token balance after the transfer.",
         "tool_calls": [{"tool_call_id": "balance", "function_name": "shell",
                         "arguments": {"command": " ".join(command)}}],
         "observation": {"results": [{"source_call_id": "balance", "content": balance}]}},
        {"step_id": 2, "source": "agent", "message": "The recipient holds 12.5 tokens. The transfer succeeded."},
    ],
}
Path("/logs/agent").mkdir(parents=True, exist_ok=True)
Path("/logs/agent/trajectory.json").write_text(json.dumps(trajectory))
