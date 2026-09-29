import json
import shutil
import subprocess

import pytest

from test_chain_docker import ROOT


pytestmark = pytest.mark.docker


def test_free_check_rejects_broken_untouched_checker(tmp_path, config_path):
    folder = tmp_path / "transactions" / "broken"
    shutil.copytree(ROOT / "evals/transactions/send-six-decimal-token", folder)
    path = folder / "scorer/check.py"
    broken = "print('invalid JSON'); raise SystemExit(0)"
    path.write_text(path.read_text().replace("sent =", f"if balance == 0:\n    {broken}\nsent ="))
    result = subprocess.run(["uv", "run", "ethevals", "check", "--evals", str(folder), "--epochs", "1",
                             "--output", str(tmp_path / "check"), "--config", str(config_path)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 1, result.stdout + result.stderr
    rows = [json.loads(line) for line in (tmp_path / "check/empty/rows.jsonl").read_text().splitlines()]
    assert [row["status"] for row in rows] == ["error"]
    references = [json.loads(line) for line in (tmp_path / "check/reference/rows.jsonl").read_text().splitlines()]
    assert [row["status"] for row in references] == ["passed"]
