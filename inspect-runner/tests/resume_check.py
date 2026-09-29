"""A slow scripted epoch for the process interruption test."""
import sys
from pathlib import Path
from ethevals.checks import CHECK_SOLVERS, CheckRun
from ethevals.loader import load_eval
from ethevals.runner import run
from support import load_config, mock_delay

original = CHECK_SOLVERS["quiz"]
def delayed(evaluation, answer):
    check = original(evaluation, answer)
    return CheckRun([mock_delay(2), check.solver], check.reply)

CHECK_SOLVERS["quiz"] = delayed
folder, output, config_path = map(Path, sys.argv[1:])
config = load_config(config_path)
success, _ = run([load_eval(folder, config)], config, output, answer="reference", epochs=3)
raise SystemExit(0 if success else 1)
