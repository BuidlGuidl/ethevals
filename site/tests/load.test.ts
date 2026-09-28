import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import test, { type TestContext } from "node:test";
import { loadBoard } from "../src/load";
import { siteRoot } from "../src/paths";
import type { Row } from "../src/rows";

const evaluation = {
  id: "concepts/units", hash: "current", pillar: "concepts", type: "quiz",
  prompt: "How many wei?", motivation: "Check units.", modes: ["internet", "vanilla", "skills"], choices: null,
};
const paid: Row = {
  schema_version: 2, eval_id: "concepts/units", eval_hash: "current", pillar: "concepts", type: "quiz",
  model: "model-a", harness: "harness-a", effort: "high", mode: "internet", answer_kind: null,
  epoch: 1, status: "passed", passed: true, checks: { answer: { passed: true, reason: "Matches." } },
  error_kind: null, error_reason: null, total_tokens: 100, token_source: "provider",
  model_cost_usd: 0.2, grader_cost_usd: 0.05, model_cost_source: "computed", grader_cost_source: "computed",
  total_seconds: 8, working_seconds: 7, log_file: "logs/epoch.eval",
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
  writeFileSync(path.join(site, ".catalog/catalog.json"), JSON.stringify([evaluation]));
  const rows = path.join(root, "results/rows.jsonl");
  return { root, site, rows, write: (values: Partial<Row>[]) => {
    writeFileSync(rows, "\n" + values.map((value) => JSON.stringify({ ...paid, ...value })).join("\n"));
  } };
}

for (const [name, change, message] of [
  ["undeclared mode", { mode: "vanilla", harness: null }, "does not declare this mode"],
  ["wrong pillar", { pillar: "security" }, "pillar differs"],
  ["wrong type", { type: "scenario" }, "type differs"],
  ["internet without harness", { harness: null }, "require a harness"],
  ["vanilla with harness", { mode: "vanilla" }, "cannot have a harness"],
  ["vanilla non-quiz", { mode: "vanilla", harness: null, type: "build" }, "require a quiz"],
] as const) {
  test(`loader rejects ${name} with the file and physical line`, (t) => {
    const f = fixture(t);
    writeFileSync(path.join(f.site, ".catalog/catalog.json"), JSON.stringify([{ ...evaluation, modes: ["internet"] }]));
    f.write([change]);
    assert.throws(() => loadBoard({}, f.site), (error: Error) =>
      error.message.startsWith(`${f.rows}:2:`) && error.message.includes(message));
  });
}

test("loader reports duplicate identities even among excluded rows and preserves answer kinds", (t) => {
  const f = fixture(t);
  f.write([{}, { answer_kind: "reference" }, { answer_kind: "empty" }]);
  assert.equal(loadBoard({}, f.site).tables.internet.pillars.concepts.cells['["model-a","harness-a","high"]'].score, 1);
  for (const change of [{}, { answer_kind: "reference" }, { eval_hash: "old" }]) {
    f.write([change, change]);
    assert.throws(() => loadBoard({}, f.site), (error: Error) =>
      error.message.startsWith(`${f.rows}:3: Duplicate epoch`));
  }
});

test("loader excludes key-free, stale, and skills rows and prints their counts", (t) => {
  const f = fixture(t);
  f.write([{}, { epoch: 2, answer_kind: "reference" }, { epoch: 3, answer_kind: "empty" },
    { epoch: 4, answer_kind: "default" }, { epoch: 5, token_source: "mock" },
    { epoch: 6, eval_hash: "old", pillar: "security", type: "scenario" }, { epoch: 7, mode: "skills" }]);
  const messages: string[] = [];
  t.mock.method(console, "log", (message: string) => messages.push(message));
  const board = loadBoard({}, f.site);
  assert.deepEqual(messages, [`${f.rows}: 7 read, 1 shown, 1 stale, 4 key-free, 1 skills.`]);
  assert.deepEqual(board.tables.internet.subjects, [{ model: "model-a", harness: "harness-a", effort: "high" }]);
  const cell = board.tables.internet.pillars.concepts.evals[0].cells['["model-a","harness-a","high"]'];
  assert.deepEqual([cell.passed, cell.total, cell.score], [1, 1, 1]);
  assert.deepEqual(board.evaluations["concepts/units"].choices, []);
  assert.deepEqual(Object.keys(cell.epochs[0]).sort(), [
    "checks", "cost", "epoch", "error_kind", "error_reason", "grader_cost_source", "grader_cost_usd",
    "issue", "logUrl", "model_cost_source", "model_cost_usd", "status", "total_seconds", "total_tokens",
  ]);
});

test("missing default rows give an explicit empty state, while an override is required to exist", (t) => {
  const f = fixture(t);
  const messages: string[] = [];
  t.mock.method(console, "log", (message: string) => messages.push(message));
  const empty = loadBoard({}, f.site);
  assert.deepEqual([empty.tables.internet.subjects.length, empty.tables.vanilla.subjects.length,
    empty.evaluations["concepts/units"].prompt], [0, 0, "How many wei?"]);
  assert.equal(messages[0], `${f.rows} (missing; empty board): 0 read, 0 shown, 0 stale, 0 key-free, 0 skills.`);
  assert.throws(() => loadBoard({ ETHEVALS_ROWS: "../results/typo.jsonl" }, f.site), /typo.jsonl: results file does not exist/);
  f.write([{}]);
  assert.equal(loadBoard({ ETHEVALS_ROWS: "../results/rows.jsonl" }, f.site).tables.internet.subjects[0].model, "model-a");
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

test("log base rejects unsafe values and produces a published link for a valid URL", (t) => {
  const f = fixture(t);
  f.write([{}]);
  for (const base of ["javascript:alert(1)", "//elsewhere.test", "relative/logs"]) {
    assert.throws(() => loadBoard({ ETHEVALS_LOG_BASE: base }, f.site), /ETHEVALS_LOG_BASE must be an HTTP URL/);
  }
  const board = loadBoard({ ETHEVALS_LOG_BASE: "https://example.org/results" }, f.site);
  assert.equal(board.tables.internet.pillars.concepts.evals[0].cells['["model-a","harness-a","high"]'].epochs[0].logUrl,
    "https://example.org/results/logs/epoch.eval");
});

test("default site paths do not depend on the process working directory", () => {
  const previous = process.cwd();
  try {
    process.chdir(path.dirname(siteRoot));
    const board = loadBoard({ ETHEVALS_SAMPLE: "1" });
    assert.equal(board.tables.internet.pillars.concepts.cells['["Sample model A","Sample harness A","high"]'].score, 0.8333333333333333);
  } finally {
    process.chdir(previous);
  }
});
