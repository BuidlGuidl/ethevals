import assert from "node:assert/strict";
import test from "node:test";
import { agentKey, buildBoard, type Eval, type Row } from "./board";
import { drawerRefusalBanner, ignoreRefusals, refusalLines, refusals, refusalStrip, tableHasRefusals, taskRefusalLines } from "./refusals";

const agent = { model: "model-a", agent: "agent-a", effort: null };
const key = agentKey(agent);
const build = (id: string): Eval => ({
  id: `build/${id}`, title: id, pillar: "build", hash: "h", instruction_hash: "h", environment_hash: "h", checks_hash: "h",
  description: "Build it.", instruction: "Build it.", modes: ["internet"], checks: { finding_a: "judgment", finding_b: "judgment" },
});
const concepts: Eval = { ...build("units"), id: "concepts/units", pillar: "concepts", checks: undefined };
const pass = { passed: true, reason: "Yes." }, fail = { passed: false, reason: "No." };

function row(task: Eval, trial: number, overrides: Partial<Row> = {}): Row {
  return {
    ...agent, schema_version: 8, task_id: task.id, task_hash: "h", instruction_hash: "h", environment_hash: "h", checks_hash: "h",
    skills_hash: null, mode: "internet", trial, status: "passed", checks: task.pillar === "concepts" ? { answer: pass } : { finding_a: pass, finding_b: pass },
    error_kind: null, error_reason: null, total_tokens: 0, model_cost_usd: 1, judge_cost_usd: 0, paid_by: "api_key", judge: null,
    judge_paid_by: null, cost_source: "harbor", total_seconds: 1, working_seconds: 1, trajectory_url: null, limit: null, ...overrides,
  };
}
const refusedTwice: Partial<Row> = { status: "failed", checks: { no_answer: { passed: false, reason: "No answer twice." } },
  no_answer: [{ kind: "refused", stop_reason: "AgentSafetyRefusalError" }, { kind: "refused", stop_reason: "AgentSafetyRefusalError" }] };
const half = { status: "failed", checks: { finding_a: pass, finding_b: fail } } as const;

const [x, y, z] = [build("x"), build("y"), build("z")];
// x: one refusal and one 100% trial. y: refused twice on both trials. z: one 50% trial.
const board = buildBoard([concepts, x, y, z], [
  row(concepts, 1), row(x, 1, refusedTwice), row(x, 2), row(y, 1, refusedTwice), row(y, 2, refusedTwice), row(z, 1, half),
]);

test("ignoring refusals drops refused trials, then recomputes task, pillar and Overall scores", () => {
  // Overall counts one Concepts task and three Build tasks.
  assert.deepEqual(board.tables.internet.summaries[key].scores, { overall: (1 * 1 + 3 * (1 / 3)) / 4, concepts: 1, build: 1 / 3, act: null });
  const ignored = ignoreRefusals(board).tables.internet;
  const cells = ignored.pillars.build.evals.map((entry) => entry.cells[key].score);
  // Task y has no scored trial left, so it leaves the Build average like an unrun task.
  assert.deepEqual(cells, [1, null, 0.5]);
  // Build keeps its weight of three tasks: weights come from the task list, not from the scored tasks.
  assert.deepEqual(ignored.summaries[key].scores, { overall: (1 * 1 + 3 * 0.75) / 4, concepts: 1, build: 0.75, act: null });
  assert.equal(ignored.pillars.build.cells[key].scoredEvals, 2);
});

test("refusal lines state skipped tasks without raw trial counts, while drawer banners keep trial counts", () => {
  const ignored = ignoreRefusals(board).tables.internet;
  const buildInfo = refusals(ignored, key, "build");
  assert.deepEqual(buildInfo, { refused: 3, without: 0.75, coverage: [{ pillar: "build", scored: 2, tasks: 3 }] });
  assert.deepEqual(refusalLines(buildInfo, false), ["Safety refusals scored as 0%", "Without refusals: 75.0% (1 of 3 Build tasks skipped)"]);
  assert.deepEqual(refusalLines(buildInfo, true), ["Safety refusals ignored", "1 of 3 Build tasks skipped"]);
  assert.deepEqual(refusalLines({ refused: 1, without: 0.9, coverage: [{ pillar: "build", scored: 3, tasks: 3 }] }, false),
    ["Safety refusals scored as 0%", "Without refusals: 90.0% (all 3 Build tasks still scored)"]);
  assert.deepEqual(refusalLines({ refused: 1, without: 0.9, coverage: [{ pillar: "build", scored: 3, tasks: 3 }] }, true),
    ["Safety refusals ignored", "All 3 Build tasks still scored"]);
  assert.equal(drawerRefusalBanner(buildInfo, false), "3 refused trials (scored as 0%).");
  assert.equal(drawerRefusalBanner(buildInfo, true), "3 refused trials ignored. 1 of 3 Build tasks skipped.");
  assert.equal(refusals(ignored, key, "overall").without, (1 * 1 + 3 * 0.75) / 4);
  assert.equal(refusals(ignored, key, "concepts").refused, 0);
  const [xIgnored, yIgnored] = ignored.pillars.build.evals.map((entry) => entry.cells[key]);
  assert.deepEqual(taskRefusalLines(board.tables.internet.pillars.build.evals[1].cells[key], false), ["2 refused trials (scored as 0%)"]);
  assert.deepEqual(taskRefusalLines(yIgnored, true), ["2 refused trials ignored", "No scored trials left"]);
  assert.deepEqual(taskRefusalLines(xIgnored, true), ["1 refused trial ignored"]);
  assert.equal(refusalStrip(ignored), "Ignoring 3 safety-refused trials across 1 agent. Tasks left without a scored trial are left out of averages.");
});

test("a refusal answered on retry, an empty reply twice, and errors are not refusals", () => {
  const other = buildBoard([x], [
    row(x, 1, { no_answer: [{ kind: "refused", stop_reason: "AgentSafetyRefusalError" }] }),
    row(x, 2, { ...refusedTwice, no_answer: [{ kind: "empty", stop_reason: "stop" }, { kind: "empty", stop_reason: "stop" }] }),
    row(x, 3, { status: "error", checks: {}, error_kind: "execution", error_reason: "Stopped." }),
  ], false, 4);
  assert.equal(tableHasRefusals(other.tables.internet), false);
  assert.deepEqual(ignoreRefusals(other).tables.internet.summaries[key], other.tables.internet.summaries[key]);
  assert.equal(refusals(other.tables.internet, key, "overall").refused, 0);
  assert.equal(tableHasRefusals(board.tables.internet), true);
});

test("ignoring refusals keeps refused trials listed and leaves unscored counts alone", () => {
  const withError = buildBoard([x], [row(x, 1, refusedTwice), row(x, 2, { status: "error", checks: {}, error_kind: "execution", error_reason: "Stopped." })], false, 2);
  const cell = ignoreRefusals(withError).tables.internet.pillars.build.evals[0].cells[key];
  assert.equal(cell.trials.length, 2);
  assert.deepEqual(cell.trials.map((trial) => trial.ignored ?? false), [true, false]);
  assert.equal(cell.score, null);
  assert.equal(cell.missing, withError.tables.internet.pillars.build.evals[0].cells[key].missing);
});
