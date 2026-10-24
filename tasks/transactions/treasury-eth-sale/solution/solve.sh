#!/bin/sh
set -eu
cd /workspace
test -r chain_context.json
test ! -r /private/private_chain_context.json
cp /solution/sell_eth.py /workspace/sell_eth.py
python3 /workspace/sell_eth.py
python3 - <<'PY'
import json
from pathlib import Path

sale = json.loads(Path("sale.json").read_text())
trajectory = {
    "schema_version": "ATIF-v1.7", "session_id": "solution",
    "agent": {"name": "oracle", "version": "1.0.0"},
    "steps": [{
        "step_id": 1, "source": "agent",
        "message": "Ran the quarterly script with a Chainlink minimum, a deadline, and a quarter lock. Checked receipt status before writing sale.json.",
        "tool_calls": [{"tool_call_id": "sale", "function_name": "shell",
                        "arguments": {"command": "python3 /workspace/sell_eth.py"}}],
        "observation": {"results": [{"source_call_id": "sale", "content": json.dumps(sale)}]},
    }],
}
Path("/logs/agent").mkdir(parents=True, exist_ok=True)
Path("/logs/agent/trajectory.json").write_text(json.dumps(trajectory) + "\n")
PY
