import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Detail, Results } from "../app/board";
import { loadCatalog, parseRows } from "../src/load";
import { agentKey, buildBoard } from "../src/board";
import { siteRoot } from "../src/paths";

for (const withCriteria of [false, true]) test(`a real Harbor row reaches the board and drawer, criteria=${withCriteria}`, (t) => {
  const scratch = path.join(siteRoot, ".test-tmp");
  mkdirSync(scratch, { recursive: true });
  const root = mkdtempSync(path.join(scratch, "harbor-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const repo = path.dirname(siteRoot);
  const fixture = path.join(repo, "runner/tests/fixtures/harbor");
  const env = { ...process.env };
  for (const key of ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY"]) delete env[key];
  const script = `
import asyncio
import json
import shutil
from pathlib import Path
import litellm
from ethevals.judge import JudgeSettings, judge_trial
from ethevals.jobs import write_catalog, task_entry
from ethevals.trial_rows import results_row, write_rows
fixture, output = Path(${JSON.stringify(fixture)}), Path(${JSON.stringify(root)})
task, trial = output / "question", output / "trial"
shutil.copytree(fixture / "question", task)
shutil.copytree(fixture / "recorded-trial", trial)
metadata = json.loads((fixture / "recorded-trial/board.json").read_text())
if ${withCriteria ? "True" : "False"}:
    (task / "tests/criteria.md").write_text("## named_unit\\nDid the reply name a unit?\\n")
    (trial / "artifacts/logs/agent").mkdir(parents=True)
    shutil.copyfile(trial / "agent/trajectory.json", trial / "artifacts/logs/agent/trajectory.json")
    settings = JudgeSettings(model="openai/gpt-5", paid_by="free")
    metadata.update(judge={"model": settings.model, "effort": settings.effort}, criteria_names=["named_unit"])
    async def completion(**kwargs):
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content":
            '{"score":"yes","reasoning":"The reply names the unit metre."}'}}])
    litellm.acompletion = completion
    asyncio.run(judge_trial(trial, task, settings))
write_catalog([task], output)
metadata["task_hash"] = task_entry(task)["hash"]
write_rows(output / "rows.jsonl", [results_row(trial, metadata,
    trajectory_url="https://example.org/trials/oracle/trajectory.json")])
`;
  const result = spawnSync("uv", ["run", "python", "-c", script], { cwd: repo, env, encoding: "utf8", timeout: 60_000 });
  assert.equal(result.status, 0, result.error?.message ?? result.stderr + result.stdout);
  const { evals } = loadCatalog(path.join(root, "catalog.json"));
  const rows = parseRows(readFileSync(path.join(root, "rows.jsonl"), "utf8"), "rows.jsonl", evals);
  assert.deepEqual(rows.map((row) => [row.task_id, row.schema_version, row.status, row.paid_by, row.model_cost_usd]),
    [["concepts/question", 7, "passed", "free", 0]]);
  assert.deepEqual(rows[0].checks, {
    unit: { passed: true, reason: "The final reply matches." },
    ...(withCriteria ? { named_unit: { passed: true, reason: "The reply names the unit metre." } } : {}),
  });
  assert.deepEqual(rows[0].judge, withCriteria ? { model: "openai/gpt-5", effort: "high" } : null);
  const data = buildBoard(evals, rows);
  const agent = data.tables.internet.agents[0];
  const cell = data.tables.internet.pillars.concepts.evals[0].cells[agentKey(agent)];
  assert.deepEqual([cell.passed, cell.total], [1, 1]);
  const html = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams() }));
  assert.ok(html.includes("1 of 1 trials passed"));
  const drawer = renderToStaticMarkup(createElement(Detail, {
    data, selection: { agent, evaluation: data.evaluations["concepts/question"], mode: "internet", run: 1 }, onSelect: () => {},
  }));
  assert.ok(drawer.includes('href="https://example.org/trials/oracle/trajectory.json" target="_blank" rel="noreferrer">Open trajectory ↗'));
  assert.ok(drawer.includes("No model spend"));
  if (withCriteria) {
    assert.ok(drawer.includes("named_unit"));
    assert.ok(drawer.includes("The reply names the unit metre."));
  }
});
