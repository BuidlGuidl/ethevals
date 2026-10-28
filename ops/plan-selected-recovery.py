"""Plan the seven trials selected on October 28 with the existing CI planner."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ci


SELECTION = [
    ("build/token-lending-market", "codex-gpt-6.1-sol", 1),
    ("build/swap-page", "codex-gpt-6.1-sol", 1),
    ("build/signed-votes", "codex-gpt-6-astra", 1),
    ("build/swap-page", "opencode-deepseek-v4.1-flash-1017", 2),
    ("concepts/wallet-batch-status-600", "opencode-gemini-4-argon", 1),
    ("concepts/wallet-batch-status-600", "opencode-gemini-4-argon", 2),
    ("concepts/wallet-batch-status-600", "opencode-grok-4.7", 2),
]
BUDGET = 188.0
SOURCE_COMMIT = "a976a77ae8c3943c1611359d1e169ce1101a8971"

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--github-output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
rows = args.output / "rows.jsonl"
ci.write_rows(rows, ci.result_record(ci.read_rows(Path(__file__).with_name("selected-recovery-rows.jsonl"))))
scheduled, matrix = [], []
for index, (task, agent, trial) in enumerate(SELECTION):
    part = args.output / "selections" / str(index)
    outputs = args.output / f"selection-{index}.txt"
    status = ci.plan_trials(
        argparse.Namespace(output=part, restore_results=False, github_output=outputs),
        ["--tasks", f"tasks/{task}", "--agents", agent, "--modes", "internet",
         "--trial", str(trial), "--rows", str(rows), "--budget", str(BUDGET)],
    )
    if status:
        raise RuntimeError(f"Planning failed for {task}, {agent}, trial {trial}")
    report = json.loads((part / "plan.json").read_text())
    if report["deferred"] or report["exhausted_errors"]:
        raise RuntimeError(f"The selected trial cannot run: {task}, {agent}, trial {trial}")
    entries = json.loads((part / "trials.json").read_text())
    fields = dict(line.split("=", 1) for line in outputs.read_text().splitlines())
    for item, job in zip(entries, json.loads(fields["matrix"])["include"], strict=True):
        job["index"] = len(scheduled)
        if not job["plan_group"]:
            job["lane"] = f"key-{len(scheduled) % ci.KEY_LANES}"
        scheduled.append(item)
        matrix.append(job)
    if index == 0:
        shutil.copyfile(part / "config.json", args.output / "config.json")

report = ci.budget_check({
    "missing": [item for entry in scheduled for item in entry["missing"]],
    "selected": [identity for entry in scheduled for identity in entry["selected"]],
    "missing_trials": len(scheduled),
    "worst_case_usd": sum(entry["worst_case_usd"] for entry in scheduled),
}, BUDGET, required=True)
if not report["within_budget"]:
    raise RuntimeError("The seven-trial selection exceeds its reviewed budget")
(args.output / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
(args.output / "trials.json").write_text(json.dumps(scheduled, indent=2) + "\n")
with args.github_output.open("a") as output:
    output.write(f"matrix={json.dumps({'include': matrix}, separators=(',', ':'))}\n")
    output.write(f"scheduled_trials={len(scheduled)}\n")
    output.write(f"sha={SOURCE_COMMIT}\n")
print(f"Admitted {len(scheduled)} trials; reserve ${report['worst_case_usd']:.2f}.")
