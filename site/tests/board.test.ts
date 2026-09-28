import assert from "node:assert/strict";
import test from "node:test";
import { boardRows, epochCost, evalCell, logUrl, pillarCell, subjectsFor, type Evaluation, type Row } from "../src/board";
import { loadBoard, parseRows } from "../src/load";

const evaluation: Evaluation = {
  id: "concepts/units", hash: "current", title: "Units", pillar: "concepts", type: "quiz",
  motivation: "Check units.", prompt: "How many wei equal one ether?", choices: [], modes: ["internet", "vanilla"],
};
const subject = { model: "model-a", harness: "harness-a", effort: "high" };
function row(overrides: Partial<Row> = {}): Row {
  return {
    schema_version: 2, eval_id: "concepts/units", eval_hash: "current", pillar: "concepts", type: "quiz",
    ...subject, mode: "internet", answer_kind: null, epoch: 1, status: "passed", passed: true,
    checks: { answer: { passed: true, reason: "The answer matches." } }, error_kind: null, error_reason: null,
    total_tokens: 100, token_source: "provider", model_cost_usd: 0.2, grader_cost_usd: 0.05,
    model_cost_source: "computed", grader_cost_source: "computed", total_seconds: 8, working_seconds: 7,
    log_file: "logs/epoch.eval", ...overrides,
  };
}
const failure = { status: "failed", passed: false, checks: { answer: { passed: false, reason: "The answer differs." } } } as const;
const error = { status: "error", passed: null, checks: {}, error_kind: "execution", error_reason: "Sandbox stopped." } as const;

test("a score counts passed epochs and excludes errors, while retaining their details", () => {
  const cell = evalCell(evaluation, subject, "internet", [row(), row({ epoch: 2 }), row({ epoch: 3, ...failure }), row({ epoch: 4, ...error })]);
  assert.deepEqual({ state: cell.state, score: cell.score, passed: cell.passed, total: cell.total, errors: cell.errors },
    { state: "score", score: 2 / 3, passed: 2, total: 3, errors: 1 });
  assert.equal(cell.epochs[3].error_reason, "Sandbox stopped.");
});

test("unsupported, unrun, and failed cells have distinct states", () => {
  const na = evalCell({ ...evaluation, modes: ["vanilla"] }, subject, "internet", [row()]);
  const pending = evalCell(evaluation, subject, "internet", []);
  const failed = evalCell(evaluation, subject, "internet", [row(failure)]);
  assert.deepEqual([na, pending, failed].map(({ state, score, passed, total }) => ({ state, score, passed, total })), [
    { state: "na", score: null, passed: 0, total: 0 },
    { state: "pending", score: null, passed: 0, total: 0 },
    { state: "score", score: 0, passed: 0, total: 1 },
  ]);
});

test("an error-only cell has no score, and a time limit counts as a failure", () => {
  const pending = evalCell(evaluation, subject, "internet", [row(error)]);
  const limited = evalCell(evaluation, subject, "internet", [row({ ...failure, checks: {
    runner_time_limit: { passed: false, reason: "Epoch reached time limit 300." },
  } })]);
  assert.deepEqual([pending.state, pending.score, pending.errors], ["pending", null, 1]);
  assert.deepEqual([limited.state, limited.score, limited.total], ["score", 0, 1]);
  assert.equal(limited.epochs[0].checks.runner_time_limit.reason, "Epoch reached time limit 300.");
});

test("pillar means give evals equal weight and skip evals without scored epochs", () => {
  const cell = pillarCell([evaluation, { ...evaluation, id: "concepts/b" }, { ...evaluation, id: "concepts/c" },
    { ...evaluation, id: "concepts/d", modes: ["vanilla"] }], subject, "internet", [
    row(), row({ eval_id: "concepts/b" }), row({ eval_id: "concepts/b", epoch: 2, ...failure }),
    row({ eval_id: "concepts/b", epoch: 3, ...failure }), row({ eval_id: "concepts/c", ...error }),
  ]);
  assert.deepEqual({ score: cell.score, passed: cell.passed, total: cell.total, scoredEvals: cell.scoredEvals, errors: cell.errors },
    { score: 2 / 3, passed: 2, total: 4, scoredEvals: 2, errors: 1 });
});

test("reference, empty, default mock, and stale rows never enter a score or a subject column", () => {
  const rows = [row(failure), row({ epoch: 2, answer_kind: "reference" }), row({ epoch: 3, answer_kind: "empty" }),
    row({ epoch: 4, answer_kind: "default" }), row({ epoch: 5, token_source: "mock" }), row({ epoch: 6, eval_hash: "old" })];
  const cell = evalCell(evaluation, subject, "internet", rows);
  assert.deepEqual([cell.passed, cell.total, cell.score], [0, 1, 0]);
  assert.deepEqual(boardRows([evaluation], rows).map((item) => item.epoch), [1]);
  assert.deepEqual(subjectsFor(boardRows([evaluation], rows), "internet"), [subject]);
});

test("mode, harness, model, and effort keep different subjects apart", () => {
  const rows = [row(), row({ model: "model-b", ...failure }), row({ harness: "harness-b", ...failure }),
    row({ effort: "low", ...failure }), row({ mode: "vanilla", harness: null, ...failure })];
  const agent = evalCell(evaluation, subject, "internet", rows);
  const bare = evalCell(evaluation, { ...subject, harness: null }, "vanilla", rows);
  assert.deepEqual([agent.passed, agent.total, bare.passed, bare.total], [1, 1, 0, 1]);
  assert.deepEqual(subjectsFor(boardRows([evaluation], rows), "vanilla"), [{ model: "model-a", harness: null, effort: "high" }]);
});

test("the knowledge table accepts only bare models on quiz evals", () => {
  const build = { ...evaluation, id: "concepts/build", type: "build" as const };
  const rows = [row({ mode: "vanilla", harness: null }), row({ epoch: 2, mode: "vanilla" }),
    row({ mode: "vanilla", harness: null, eval_id: "concepts/build", type: "build" })];
  assert.deepEqual(boardRows([evaluation, build], rows).map((item) => [item.eval_id, item.epoch]), [["concepts/units", 1]]);
});

test("cost adds both roles and keeps a missing price unknown", () => {
  assert.equal(epochCost(row()), 0.25);
  assert.equal(epochCost(row({ grader_cost_usd: null })), null);
  assert.equal(epochCost(row({ model_cost_usd: null })), null);
  assert.equal(epochCost(row({ model_cost_usd: 0, grader_cost_usd: 0 })), 0);
});

test("log links resolve from one base and cannot escape it", () => {
  assert.equal(logUrl("https://example.org/release/", "logs/epoch one.eval"), "https://example.org/release/logs/epoch%20one.eval");
  assert.equal(logUrl("/results", "logs/epoch.eval"), "/results/logs/epoch.eval");
  assert.equal(logUrl("", "logs/epoch.eval"), null);
  assert.equal(logUrl("/results", "../secret"), null);
  assert.equal(logUrl("/results", "https://elsewhere.test/a"), null);
});

test("row parsing keeps long named-check reasons and reports malformed verdicts with a line number", () => {
  const reason = "The expected answer differs. ".repeat(60).trim();
  assert.equal(parseRows(JSON.stringify(row({ ...failure, checks: { answer: { passed: false, reason } } })), "results.jsonl")[0].checks.answer.reason, reason);
  assert.throws(() => parseRows(`\n${JSON.stringify(row({ passed: false }))}`, "results.jsonl"), /results.jsonl:2:.*[\s\S]*Status, verdict, and checks disagree/);
});

test("sample loading is explicit and produces scores from fixture rows and eval folders", () => {
  const data = loadBoard({ ETHEVALS_SAMPLE: "1" });
  const evaluation = data.evaluations.find((item) => item.id === "concepts/agent-registries")!;
  const cell = evalCell(evaluation, { model: "Sample model A", harness: "Sample harness A", effort: "high" }, "internet", data.rows);
  assert.deepEqual([data.sample, cell.passed, cell.total, cell.score], [true, 2, 3, 2 / 3]);
  assert.throws(() => loadBoard({ ETHEVALS_SAMPLE: "true" }), /ETHEVALS_SAMPLE must be 0 or 1/);
  assert.throws(() => loadBoard({ ETHEVALS_SAMPLE: "1", ETHEVALS_ROWS: "rows.jsonl" }), /Choose ETHEVALS_SAMPLE or ETHEVALS_ROWS/);
});
