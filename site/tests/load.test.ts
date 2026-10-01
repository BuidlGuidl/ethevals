import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import test, { type TestContext } from "node:test";
import { loadBoard, parseRows } from "../src/load";
import { siteRoot } from "../src/paths";
import type { Row } from "../src/rows";

const evaluation = {
  id: "concepts/units", hash: "current", pillar: "concepts",
  prompt: "How many wei?", motivation: "Check units.", modes: ["internet", "vanilla", "skills"], choices: null,
};
const paid: Row = {
  schema_version: 6, eval_id: "concepts/units", eval_hash: "current", skills_hash: null,
  model: "model-a", harness: "harness-a", effort: "high", mode: "internet",
  epoch: 1, status: "passed", checks: { answer: { passed: true, reason: "Matches." } },
  error_kind: null, error_reason: null, total_tokens: 100,
  model_cost_usd: 0.2, grader_cost_usd: 0.05, cost_source: "computed",
  total_seconds: 8, working_seconds: 7, log_url: null, limit: null,
};

function fixture(t: TestContext) {
  const scratch = path.join(siteRoot, ".test-tmp");
  mkdirSync(scratch, { recursive: true });
  const root = mkdtempSync(path.join(scratch, "loader-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const site = path.join(root, "site");
  mkdirSync(path.join(site, ".catalog"), { recursive: true });
  mkdirSync(path.join(root, "evals"));
  mkdirSync(path.join(root, "results"));
  writeFileSync(path.join(site, ".catalog/catalog.json"), JSON.stringify({ skills_hash: "current-pack", evals: [evaluation] }));
  const rows = path.join(root, "results/rows.jsonl");
  return { root, site, rows, write: (values: Partial<Row>[]) => {
    writeFileSync(rows, "\n" + values.map((value) => JSON.stringify({ ...paid,
      skills_hash: value.mode === "skills" ? "current-pack" : null, ...value })).join("\n"));
  } };
}

for (const [name, change, message] of [
  ["undeclared mode", { mode: "vanilla", harness: null }, "does not declare this mode"],
  ["internet without harness", { harness: null }, "require a harness"],
  ["vanilla with harness", { mode: "vanilla" }, "cannot have a harness"],
  ["skills without pack hash", { mode: "skills", skills_hash: null }, "require a pack hash"],
  ["internet with pack hash", { skills_hash: "current-pack" }, "other modes require null"],
] as const) {
  test(`loader rejects ${name} with the file and physical line`, (t) => {
    const f = fixture(t);
    writeFileSync(path.join(f.site, ".catalog/catalog.json"), JSON.stringify({ skills_hash: "current-pack",
      evals: [{ ...evaluation, modes: ["internet"] }] }));
    f.write([change]);
    assert.throws(() => loadBoard({}, f.site), (error: Error) =>
      error.message.startsWith(`${f.rows}:2:`) && error.message.includes(message));
  });
}

test("loader reports duplicate identities even among excluded rows", (t) => {
  const f = fixture(t);
  f.write([{}]);
  assert.equal(loadBoard({}, f.site).tables.internet.pillars.concepts.cells['["model-a","harness-a","high"]'].score, 1);
  for (const change of [{}, { eval_hash: "old" }]) {
    f.write([change, change]);
    assert.throws(() => loadBoard({}, f.site), (error: Error) =>
      error.message.startsWith(`${f.rows}:3: Duplicate epoch`));
  }
});

test("loader accepts v6 rows, ignores unused metadata, and skips older rows", (t) => {
  const f = fixture(t);
  writeFileSync(f.rows, JSON.stringify({ ...paid, attempt: 2, max_attempts: 2,
    model_metered_usd: 9, grader_metered_usd: 8, harness_version: "1.0", images: { default: "image:1" } }));
  const cell = loadBoard({}, f.site).tables.internet.pillars.concepts.evals[0].cells['["model-a","harness-a","high"]'];
  assert.deepEqual([cell.score, cell.total, cell.epochs[0].cost], [1, 1, 0.25]);
  assert.equal("attempt" in cell.epochs[0], false);
  assert.equal("model_metered_usd" in cell.epochs[0], false);
  assert.deepEqual(parseRows(JSON.stringify({ ...paid, schema_version: 5 }) + "\n" + JSON.stringify(paid), "rows.jsonl", []), [paid]);
});

test("v6 cost limits retain runner reasons and count as failed epochs", (t) => {
  const f = fixture(t);
  f.write([{ status: "failed", limit: { type: "cost", limit: 5, reason: "Budget spent." },
    checks: { answer: { passed: false, reason: "Epoch reached cost limit 5.0. Budget spent." } } }]);
  const cell = loadBoard({}, f.site).tables.internet.pillars.concepts.evals[0].cells['["model-a","harness-a","high"]'];
  assert.deepEqual([cell.score, cell.total, cell.errors, cell.epochs[0].issue],
    [0, 1, 0, "Epoch reached cost limit 5.0. Budget spent."]);
});

test("loader excludes stale rows and keeps skills in a separate agent table", (t) => {
  const f = fixture(t);
  f.write([{}, { epoch: 2, eval_hash: "old" }, { epoch: 3, mode: "skills" },
    { epoch: 3, mode: "skills", skills_hash: "old-pack" }]);
  const board = loadBoard({}, f.site);
  const cell = board.tables.internet.pillars.concepts.evals[0].cells['["model-a","harness-a","high"]'];
  assert.deepEqual([cell.passed, cell.total, cell.score], [1, 1, 1]);
  assert.deepEqual(board.tables.internet.agents, [{ model: "model-a", harness: "harness-a", effort: "high" }]);
  const skills = board.tables.skills.pillars.concepts.evals[0].cells['["model-a","harness-a","high"]'];
  assert.deepEqual([skills.passed, skills.total, skills.epochs[0].epoch], [1, 1, 3]);
  f.write([{ mode: "skills", harness: null }]);
  assert.throws(() => loadBoard({}, f.site), /Agent rows require a harness/);
});

test("missing default rows give an explicit empty state, while an override is required to exist", (t) => {
  const f = fixture(t);
  const messages: string[] = [];
  t.mock.method(console, "log", (message: string) => messages.push(message));
  const empty = loadBoard({}, f.site);
  assert.deepEqual([empty.tables.internet.agents.length, empty.tables.vanilla.agents.length,
    empty.evaluations["concepts/units"].prompt], [0, 0, "How many wei?"]);
  assert.equal(messages[0], `${f.rows} (missing; empty board): 0 read, 0 current, 0 stale.`);
  assert.throws(() => loadBoard({ ETHEVALS_ROWS: "../results/typo.jsonl" }, f.site), /typo.jsonl: results file does not exist/);
  f.write([{}]);
  assert.equal(loadBoard({ ETHEVALS_ROWS: "../results/rows.jsonl" }, f.site).tables.internet.agents[0].model, "model-a");
});

test("missing eval roots and missing or malformed catalogs fail loudly", (t) => {
  const f = fixture(t);
  const catalog = path.join(f.site, ".catalog/catalog.json");
  rmSync(path.join(f.root, "evals"), { recursive: true });
  assert.throws(() => loadBoard({}, f.site), /evals: evals root does not exist/);
  mkdirSync(path.join(f.root, "evals"));
  rmSync(catalog);
  assert.throws(() => loadBoard({}, f.site), /catalog.json: cannot load eval catalog/);
  writeFileSync(catalog, "[]");
  assert.throws(() => loadBoard({}, f.site), /catalog.json: cannot load eval catalog/);
});

test("published URLs reach the board and unsafe URLs fail with a line number", (t) => {
  const f = fixture(t);
  f.write([{ log_url: "https://example.org/results/epoch.eval" }, { epoch: 2 }]);
  const board = loadBoard({}, f.site);
  const cell = board.tables.internet.pillars.concepts.evals[0].cells['["model-a","harness-a","high"]'];
  assert.deepEqual(cell.epochs.map((epoch) => epoch.logUrl), ["https://example.org/results/epoch.eval", null]);
  f.write([{ log_url: "javascript:alert(1)" }]);
  assert.throws(() => loadBoard({}, f.site), /rows.jsonl:2:/);
});

test("default site paths do not depend on the process working directory", () => {
  const previous = process.cwd();
  try {
    process.chdir(path.dirname(siteRoot));
    const board = loadBoard({ ETHEVALS_DEMO: "1" });
    assert.equal(board.tables.internet.pillars.concepts.cells['["Demo model A","Demo harness A","high"]'].score, 0.8333333333333333);
  } finally {
    process.chdir(previous);
  }
});

test("committed errors remain visible without unpublished release links", (t) => {
  const f = fixture(t);
  f.write([{ log_url: "https://github.com/example/ethevals/releases/download/results-1/epoch.eval" }, { epoch: 2, status: "error",
    error_kind: "execution", error_reason: "Provider unavailable." }]);
  const board = loadBoard({}, f.site);
  const cell = board.tables.internet.pillars.concepts.evals[0].cells['["model-a","harness-a","high"]'];
  assert.deepEqual([cell.passed, cell.total, cell.errors], [1, 1, 1]);
  assert.equal(cell.epochs[0].logUrl, "https://github.com/example/ethevals/releases/download/results-1/epoch.eval");
  assert.equal(cell.epochs[1].logUrl, null);
  assert.equal(cell.epochs[1].error_reason, "Provider unavailable.");
});
