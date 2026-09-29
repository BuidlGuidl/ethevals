import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Board, { Detail } from "../app/board";
import { buildBoard, epochCost, agentKey, type Eval, type Row, type Agent } from "../src/board";
import { loadBoard, parseRows } from "../src/load";

const evaluation: Eval = {
  id: "concepts/units", hash: "current", title: "Units", pillar: "concepts", type: "quiz",
  motivation: "Check units.", prompt: "How many wei equal one ether?", choices: [], modes: ["internet", "vanilla"],
};
const agent = { model: "model-a", harness: "harness-a", effort: "high" };
function row(overrides: Partial<Row> = {}): Row {
  return {
    schema_version: 4, eval_id: "concepts/units", eval_hash: "current", type: "quiz",
    ...agent, mode: "internet", epoch: 1, status: "passed",
    checks: { answer: { passed: true, reason: "The answer matches." } }, error_kind: null, error_reason: null,
    total_tokens: 100, model_cost_usd: 0.2, grader_cost_usd: 0.05,
    cost_source: "computed", total_seconds: 8, working_seconds: 7,
    log_url: null, limit: null, ...overrides,
  };
}

function getCell(evaluation: Eval, agent: Agent, mode: "internet" | "vanilla", rows: Row[]) {
  return buildBoard([evaluation], rows).tables[mode].pillars[evaluation.pillar].evals[0].cells[agentKey(agent)];
}

const failure = { status: "failed", checks: { answer: { passed: false, reason: "The answer differs." } } } as const;
const error = { status: "error", checks: {}, error_kind: "execution", error_reason: "Sandbox stopped." } as const;

test("a score counts passed epochs and excludes errors, while retaining their details", () => {
  const cell = getCell(evaluation, agent, "internet", [row(), row({ epoch: 2 }), row({ epoch: 3, ...failure }), row({ epoch: 4, ...error })]);
  assert.deepEqual({ state: cell.state, score: cell.score, passed: cell.passed, total: cell.total, errors: cell.errors },
    { state: "score", score: 2 / 3, passed: 2, total: 3, errors: 1 });
  assert.equal(cell.epochs[3].error_reason, "Sandbox stopped.");
});

test("unsupported, unrun, and failed cells have distinct states", () => {
  const naBoard = buildBoard([{ ...evaluation, modes: ["vanilla"] }, { ...evaluation, id: "concepts/b" }], [row({ eval_id: "concepts/b" })]);
  const na = naBoard.tables.internet.pillars.concepts.evals[0].cells[agentKey(agent)];
  const pendingBoard = buildBoard([evaluation, { ...evaluation, id: "concepts/b" }], [row({ eval_id: "concepts/b" })]);
  const pending = pendingBoard.tables.internet.pillars.concepts.evals[0].cells[agentKey(agent)];
  const failed = getCell(evaluation, agent, "internet", [row(failure)]);
  assert.deepEqual([na, pending, failed].map(({ state, score, passed, total }) => ({ state, score, passed, total })), [
    { state: "na", score: null, passed: 0, total: 0 },
    { state: "pending", score: null, passed: 0, total: 0 },
    { state: "score", score: 0, passed: 0, total: 1 },
  ]);
});

test("an error-only cell has no score, and a time limit counts as a failure", () => {
  const pending = getCell(evaluation, agent, "internet", [row(error)]);
  const limited = getCell(evaluation, agent, "internet", [row({ ...failure,
    limit: { type: "time", limit: 300, reason: null }, checks: {
      answer: { passed: false, reason: "Epoch reached time limit 300." },
      second: { passed: false, reason: "Epoch reached time limit 300." },
    } })]);
  assert.deepEqual([pending.state, pending.score, pending.errors], ["pending", null, 1]);
  assert.deepEqual([limited.state, limited.score, limited.total], ["score", 0, 1]);
  assert.equal(limited.epochs[0].issue, "Epoch reached time limit 300.");
  assert.equal(limited.epochs[0].checks.answer.reason, "Epoch reached time limit 300.");
});

test("pillar means give evals equal weight and skip evals without scored epochs", () => {
  const board = buildBoard([evaluation, { ...evaluation, id: "concepts/b" }, { ...evaluation, id: "concepts/c" },
    { ...evaluation, id: "concepts/d", modes: ["vanilla"] }], [
    row(), row({ eval_id: "concepts/b" }), row({ eval_id: "concepts/b", epoch: 2, ...failure }),
    row({ eval_id: "concepts/b", epoch: 3, ...failure }), row({ eval_id: "concepts/c", ...error }),
  ]);
  const cell = board.tables.internet.pillars.concepts.cells[agentKey(agent)];
  assert.deepEqual({ score: cell.score, passed: cell.passed, total: cell.total, scoredEvals: cell.scoredEvals, errors: cell.errors },
    { score: 2 / 3, passed: 2, total: 4, scoredEvals: 2, errors: 1 });
});

test("mode, harness, model, and effort keep different agents apart", () => {
  const rows = [row(), row({ model: "model-b", ...failure }), row({ harness: "harness-b", ...failure }),
    row({ effort: "low", ...failure }), row({ mode: "vanilla", harness: null, ...failure })];
  const cell = getCell(evaluation, agent, "internet", rows);
  const bare = getCell(evaluation, { ...agent, harness: null }, "vanilla", rows);
  assert.deepEqual([cell.passed, cell.total, bare.passed, bare.total], [1, 1, 0, 1]);
  assert.deepEqual(buildBoard([evaluation], rows).tables.vanilla.agents, [{ model: "model-a", harness: null, effort: "high" }]);
});

test("the knowledge table and its panel data include only quiz evals", () => {
  const board = buildBoard([evaluation, { ...evaluation, id: "building/token", pillar: "building", type: "build", modes: ["internet"] }],
    [row({ mode: "vanilla", harness: null })]);
  assert.deepEqual(board.tables.vanilla.pillars.concepts.evals.map((entry) => entry.id), ["concepts/units"]);
  assert.deepEqual(board.tables.vanilla.pillars.building.cells['["model-a",null,"high"]'],
    { state: "empty", score: null, passed: 0, total: 0, errors: 0, scoredEvals: 0 });
  assert.equal(board.tables.internet.pillars.building.evals[0].id, "building/token");
});

test("a pillar with no declared evals for a mode differs from an unsupported eval", () => {
  const board = buildBoard([evaluation, { ...evaluation, id: "security/check", pillar: "security", modes: ["vanilla"] }], [row()]);
  assert.deepEqual(board.tables.internet.pillars.transactions.cells[agentKey(agent)],
    { state: "empty", score: null, passed: 0, total: 0, errors: 0, scoredEvals: 0 });
  assert.equal(board.tables.internet.pillars.security.cells[agentKey(agent)].state, "empty");
  assert.equal(board.tables.internet.pillars.security.evals[0].cells[agentKey(agent)].state, "na");
  assert.equal(board.tables.internet.pillars.concepts.cells[agentKey(agent)].score, 1);
});

test("the table and panel both label an empty pillar as No evals yet", () => {
  const data = buildBoard([evaluation], [row()]);
  const table = renderToStaticMarkup(createElement(Board, { data }));
  const panel = renderToStaticMarkup(createElement(Detail, {
    data, selection: { pillar: "transactions", agent, mode: "internet" },
    onSelect: () => {}, onClose: () => {},
  }));
  assert.ok(table.includes('aria-label="Transactions, model-a · harness-a. No evals yet. Open details."'));
  assert.ok(panel.includes('<p class="mono">No evals yet</p>'));
  assert.ok(panel.includes("No evals yet for this mode."));
});

test("the board labels null effort as the provider default", () => {
  const data = buildBoard([evaluation], [row({ effort: null }), row({ effort: "medium" })]);
  const html = renderToStaticMarkup(createElement(Board, { data }));
  assert.ok(html.includes("Effort: provider default"));
  assert.ok(html.includes("Effort: medium"));
});

test("cost adds both roles and keeps a missing price unknown", () => {
  assert.equal(epochCost(row()), 0.25);
  assert.equal(epochCost(row({ grader_cost_usd: null })), null);
  assert.equal(epochCost(row({ model_cost_usd: null })), null);
  assert.equal(epochCost(row({ model_cost_usd: 0, grader_cost_usd: 0 })), 0);
});

test("the agent switch and skills details use their own scores", () => {
  const data = buildBoard([{ ...evaluation, modes: ["vanilla", "internet", "skills"] }],
    [row(), row({ mode: "skills", ...failure })]);
  const html = renderToStaticMarkup(createElement(Board, { data }));
  assert.ok(html.includes('aria-label="Agent mode"'));
  assert.ok(html.includes('aria-pressed="true">Internet</button>'));
  assert.ok(html.includes('aria-pressed="false">Skills</button>'));
  const panel = renderToStaticMarkup(createElement(Detail, {
    data, selection: { evaluation, pillar: "concepts", agent, mode: "skills" },
    onSelect: () => {}, onClose: () => {},
  }));
  assert.ok(panel.includes("0%"));
  assert.ok(panel.includes("The answer differs."));
  assert.deepEqual([data.tables.internet.pillars.concepts.cells[agentKey(agent)].score,
    data.tables.skills.pillars.concepts.cells[agentKey(agent)].score], [1, 0]);
});

test("row parsing keeps long named-check reasons and reports malformed verdicts with a line number", () => {
  const reason = "The expected answer differs. ".repeat(60).trim();
  assert.equal(parseRows(JSON.stringify(row({ ...failure, checks: { answer: { passed: false, reason } } })), "results.jsonl", [evaluation])[0].checks.answer.reason, reason);
  assert.throws(() => parseRows(`\n${JSON.stringify(row({ status: "invalid" as Row["status"] }))}`, "results.jsonl", [evaluation]), /results.jsonl:2:.*[\s\S]*status/);
});

test("demo loading is explicit and produces scores from fixture rows and catalog", () => {
  const data = loadBoard({ ETHEVALS_DEMO: "1" });
  const cell = data.tables.internet.pillars.concepts.evals.find((entry) => entry.id === "concepts/agent-registries")!
    .cells['["Demo model A","Demo harness A","high"]'];
  assert.deepEqual([data.demo, cell.passed, cell.total, cell.score], [true, 2, 3, 2 / 3]);
  assert.throws(() => loadBoard({ ETHEVALS_DEMO: "true" }), /ETHEVALS_DEMO must be 0 or 1/);
  assert.throws(() => loadBoard({ ETHEVALS_DEMO: "1", ETHEVALS_ROWS: "rows.jsonl" }), /Choose ETHEVALS_DEMO or ETHEVALS_ROWS/);
});
