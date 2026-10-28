import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import test, { type TestContext } from "node:test";
import { loadBoard, parseRows } from "../src/load";
import { siteRoot } from "../src/paths";
import type { Row } from "../src/rows";

const evaluation = {
  id: "concepts/units", hash: "current", pillar: "concepts",
  instruction: "How many wei?", description: "Check units.", modes: ["internet", "vanilla", "skills"],
};
const paid: Row = {
  schema_version: 8, task_id: "concepts/units", task_hash: "current", skills_hash: null,
  model: "model-a", agent: "agent-a", effort: "high", mode: "internet",
  trial: 1, status: "passed", checks: { answer: { passed: true, reason: "Matches." } },
  error_kind: null, error_reason: null, total_tokens: 100,
  model_cost_usd: 0.2, judge_cost_usd: 0.05, paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor",
  total_seconds: 8, working_seconds: 7, trajectory_url: null, limit: null,
};

function fixture(t: TestContext) {
  const scratch = path.join(siteRoot, ".test-tmp");
  mkdirSync(scratch, { recursive: true });
  const root = mkdtempSync(path.join(scratch, "loader-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const site = path.join(root, "site");
  mkdirSync(path.join(site, ".catalog"), { recursive: true });
  mkdirSync(path.join(root, "tasks"));
  mkdirSync(path.join(root, "results"));
  writeFileSync(path.join(site, ".catalog/catalog.json"), JSON.stringify({ skills_hash: "current-pack", n_attempts: 3, models: ["model-a"], tasks: [evaluation] }));
  const rows = path.join(root, "results/rows.jsonl");
  return { root, site, rows, write: (values: Partial<Row>[]) => {
    writeFileSync(rows, "\n" + values.map((value) => JSON.stringify({ ...paid,
      skills_hash: value.mode === "skills" ? "current-pack" : null, ...value })).join("\n"));
  } };
}

for (const [name, change, message] of [
  ["undeclared mode", { mode: "vanilla", agent: null }, "does not declare this mode"],
  ["internet without agent", { agent: null }, "require an agent"],
  ["vanilla with agent", { mode: "vanilla" }, "cannot have an agent"],
  ["skills without pack hash", { mode: "skills", skills_hash: null }, "require a pack hash"],
  ["internet with pack hash", { skills_hash: "current-pack" }, "other modes require null"],
] as const) {
  test(`loader rejects ${name} with the file and physical line`, (t) => {
    const f = fixture(t);
    writeFileSync(path.join(f.site, ".catalog/catalog.json"), JSON.stringify({ skills_hash: "current-pack", n_attempts: 3,
      models: ["model-a"],
      tasks: [{ ...evaluation, modes: ["internet"] }] }));
    f.write([change]);
    assert.throws(() => loadBoard({}, f.site), (error: Error) =>
      error.message.startsWith(`${f.rows}:2:`) && error.message.includes(message));
  });
}

test("loader reports duplicate identities even among excluded rows", (t) => {
  const f = fixture(t);
  f.write([{}]);
  assert.equal(loadBoard({}, f.site).tables.internet.pillars.concepts.cells['["model-a","agent-a","high"]'].score, 1);
  for (const change of [{}, { task_hash: "old" }]) {
    f.write([change, change]);
    assert.throws(() => loadBoard({}, f.site), (error: Error) =>
      error.message.startsWith(`${f.rows}:3: Duplicate trial`));
  }
});

test("loader accepts v8 rows, ignores unused metadata, and skips older rows", (t) => {
  const f = fixture(t);
  writeFileSync(f.rows, JSON.stringify({ ...paid, retry: 1,
    model_metered_usd: 9, grader_metered_usd: 8, agent_version: "1.0", images: { default: "image:1" } }));
  const cell = loadBoard({}, f.site).tables.internet.pillars.concepts.evals[0].cells['["model-a","agent-a","high"]'];
  assert.deepEqual([cell.score, cell.total, cell.trials[0].cost], [1, 1, 0.25]);
  assert.equal("retry" in cell.trials[0], false);
  assert.equal("model_metered_usd" in cell.trials[0], false);
  assert.deepEqual(parseRows(JSON.stringify({ ...paid, schema_version: 7 }) + "\n" + JSON.stringify(paid), "rows.jsonl", []), [paid]);
});

test("v7 cost limits retain runner reasons and count as failed trials", (t) => {
  const f = fixture(t);
  f.write([{ status: "failed", limit: { type: "cost", limit: 5, reason: "Budget spent." },
    checks: { answer: { passed: false, reason: "Trial reached cost limit 5.0. Budget spent." } } }]);
  const cell = loadBoard({}, f.site).tables.internet.pillars.concepts.evals[0].cells['["model-a","agent-a","high"]'];
  assert.deepEqual([cell.score, cell.total, cell.errors, cell.trials[0].issue],
    [0, 1, 0, "Trial reached cost limit 5.0. Budget spent."]);
});

test("loader keeps trials past the job's n_attempts off the board", (t) => {
  const f = fixture(t);
  f.write([{}, { trial: 3 }, { trial: 4 }]);
  const cell = loadBoard({}, f.site).tables.internet.pillars.concepts.evals[0].cells['["model-a","agent-a","high"]'];
  assert.deepEqual(cell.trials.map((trial) => trial.trial), [1, 3]);
});

test("loader excludes stale rows and keeps skills in a separate agent table", (t) => {
  const f = fixture(t);
  f.write([{}, { trial: 2, task_hash: "old" }, { trial: 3, mode: "skills" },
    { trial: 3, mode: "skills", skills_hash: "old-pack" }]);
  const board = loadBoard({}, f.site);
  const cell = board.tables.internet.pillars.concepts.evals[0].cells['["model-a","agent-a","high"]'];
  assert.deepEqual([cell.passed, cell.total, cell.score], [1, 1, 1]);
  assert.deepEqual(board.tables.internet.agents, [{ model: "model-a", agent: "agent-a", effort: "high" }]);
  const skills = board.tables.skills.pillars.concepts.evals[0].cells['["model-a","agent-a","high"]'];
  assert.deepEqual([skills.passed, skills.total, skills.trials[0].trial], [1, 1, 3]);
  f.write([{ mode: "skills", agent: null }]);
  assert.throws(() => loadBoard({}, f.site), /Agent rows require an agent/);
});

test("missing default rows give an explicit empty state, while an override is required to exist", (t) => {
  const f = fixture(t);
  const messages: string[] = [];
  t.mock.method(console, "log", (message: string) => messages.push(message));
  const empty = loadBoard({}, f.site);
  assert.deepEqual([empty.tables.internet.agents.length, empty.tables.vanilla.agents.length,
    empty.evaluations["concepts/units"].instruction], [0, 0, "How many wei?"]);
  assert.equal(messages[0], `${f.rows} (missing; empty board): 0 read, 0 current, 0 stale.`);
  assert.throws(() => loadBoard({ ETHEVALS_ROWS: "../results/typo.jsonl" }, f.site), /typo.jsonl: results file does not exist/);
  f.write([{}]);
  assert.equal(loadBoard({ ETHEVALS_ROWS: "../results/rows.jsonl" }, f.site).tables.internet.agents[0].model, "model-a");
});

test("missing task roots and missing or malformed catalogs fail loudly", (t) => {
  const f = fixture(t);
  const catalog = path.join(f.site, ".catalog/catalog.json");
  rmSync(path.join(f.root, "tasks"), { recursive: true });
  assert.throws(() => loadBoard({}, f.site), /tasks: tasks root does not exist/);
  mkdirSync(path.join(f.root, "tasks"));
  rmSync(catalog);
  assert.throws(() => loadBoard({}, f.site), /catalog.json: cannot load task catalog/);
  writeFileSync(catalog, "[]");
  assert.throws(() => loadBoard({}, f.site), /catalog.json: cannot load task catalog/);
});

test("an empty catalog needs no legacy task root and excludes old rows", (t) => {
  const f = fixture(t);
  f.write([{}]);
  assert.equal(loadBoard({}, f.site).tables.internet.agents[0].model, "model-a");
  rmSync(path.join(f.root, "tasks"), { recursive: true });
  writeFileSync(path.join(f.site, ".catalog/catalog.json"), JSON.stringify({ skills_hash: "current-pack", n_attempts: 3, models: ["model-a"], tasks: [] }));
  f.write([{}]);
  const board = loadBoard({}, f.site);
  assert.deepEqual(board.evaluations, {});
  assert.deepEqual(board.tables.internet.agents, []);
  assert.deepEqual(board.tables.internet.pillars.concepts.evals, []);
});

test("published URLs reach the board and unsafe URLs fail with a line number", (t) => {
  const f = fixture(t);
  f.write([{ trajectory_url: "https://example.org/results/trial.json" }, { trial: 2 }]);
  const board = loadBoard({}, f.site);
  const cell = board.tables.internet.pillars.concepts.evals[0].cells['["model-a","agent-a","high"]'];
  assert.deepEqual(cell.trials.map((trial) => trial.trajectoryUrl), ["https://example.org/results/trial.json", null]);
  f.write([{ trajectory_url: "javascript:alert(1)" }]);
  assert.throws(() => loadBoard({}, f.site), /rows.jsonl:2:/);
});

test("default site paths do not depend on the process working directory", () => {
  const previous = process.cwd();
  try {
    process.chdir(path.dirname(siteRoot));
    const board = loadBoard({ ETHEVALS_DEMO: "1" });
    assert.equal(board.tables.internet.pillars.concepts.cells['["Demo model A","Demo agent A","high"]'].score, 0.8333333333333333);
  } finally {
    process.chdir(previous);
  }
});

test("committed errors remain visible without unpublished release links", (t) => {
  const f = fixture(t);
  f.write([{ trajectory_url: "https://github.com/example/ethevals/releases/download/results-1/trial.json" }, { trial: 2, status: "error",
    error_kind: "execution", error_reason: "Provider unavailable." }]);
  const board = loadBoard({}, f.site);
  const cell = board.tables.internet.pillars.concepts.evals[0].cells['["model-a","agent-a","high"]'];
  assert.deepEqual([cell.passed, cell.total, cell.errors], [1, 1, 1]);
  assert.equal(cell.trials[0].trajectoryUrl, "https://github.com/example/ethevals/releases/download/results-1/trial.json");
  assert.equal(cell.trials[1].trajectoryUrl, null);
  assert.equal(cell.trials[1].error_reason, "Provider unavailable.");
});
