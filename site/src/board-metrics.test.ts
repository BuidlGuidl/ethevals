import assert from "node:assert/strict";
import test from "node:test";
import { buildBoard, overallScore, costPerPass, skillLift, type Eval, type Row } from "./board";

test("Overall gives scored pillars equal weight and skips missing scores", () => {
  assert.equal(overallScore([1, 0.5, null, 0]), 0.5);
  assert.equal(overallScore([null, null]), null);
  assert.equal(overallScore([0, null]), 0);
});

test("cost per pass includes failed model spend, excludes errors and judge spend", () => {
  assert.equal(costPerPass([
    { status: "passed", model_cost_usd: 0.2 }, { status: "passed", model_cost_usd: 0.3 },
    { status: "failed", model_cost_usd: 0.5 }, { status: "error", model_cost_usd: 50 },
  ]), 0.5);
  assert.equal(costPerPass([{ status: "failed", model_cost_usd: 1 }]), null);
  assert.equal(costPerPass([{ status: "passed", model_cost_usd: null }]), null);
  assert.equal(costPerPass([{ status: "passed", model_cost_usd: 0 }]), 0);
});

test("lift is the signed skills minus Internet score in percentage points", () => {
  assert.equal(skillLift(0.75, 0.5), 25);
  assert.equal(skillLift(0.25, 0.5), -25);
  assert.equal(skillLift(0.5, 0.5), 0);
  assert.equal(skillLift(null, 0.5), null);
  assert.equal(skillLift(0.5, null), null);
});

test("the board publishes summaries, costs and paired lifts for each configuration", () => {
  const evals: Eval[] = [
    { id: "concepts/a", hash: "a", title: "A", pillar: "concepts", motivation: "Check A.", instruction: "A?", modes: ["internet", "skills"] },
    { id: "building/b", hash: "b", title: "B", pillar: "building", motivation: "Check B.", instruction: "B?", modes: ["internet", "skills"] },
  ];
  const base: Row = { schema_version: 7, task_id: "concepts/a", task_hash: "a", skills_hash: null, model: "m", agent: "h", effort: null,
    mode: "internet", trial: 1, status: "passed", checks: {}, error_kind: null, error_reason: null, limit: null,
    model_cost_usd: 0.5, judge_cost_usd: 90, total_tokens: 100, total_seconds: 10, working_seconds: 8, paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor", trajectory_url: null };
  const board = buildBoard(evals, [base, { ...base, task_id: "building/b", task_hash: "b", status: "failed" },
    { ...base, mode: "skills", skills_hash: "pack" }, { ...base, mode: "skills", skills_hash: "pack", task_id: "building/b", task_hash: "b" }]);
  assert.deepEqual(board.tables.internet.summaries['["m","h",null]'], {
    scores: { overall: 0.5, concepts: 1, transactions: null, building: 0, security: null },
    costPerPass: 1, medianTokens: 100, passed: 1, total: 2, errors: 0,
  });
  assert.deepEqual(board.lifts['["m","h",null]'], { overall: 50, concepts: 0, transactions: null, building: 100, security: null });
  assert.deepEqual(board.counts, { evals: 2, agents: 1, runs: 4 });
});

test("lift pairs tasks when skills covers a strict subset of Internet results", () => {
  const evaluation: Eval = { id: "concepts/a", hash: "a", title: "A", pillar: "concepts", motivation: "Check A.", instruction: "A?", modes: ["internet", "skills"] };
  const evals: Eval[] = [evaluation, { ...evaluation, id: "concepts/b" }, { ...evaluation, id: "building/c", pillar: "building" }];
  const base: Row = { schema_version: 7, task_id: "concepts/a", task_hash: "a", skills_hash: null, model: "m", agent: "h", effort: null,
    mode: "internet", trial: 1, status: "failed", checks: {}, error_kind: null, error_reason: null, limit: null,
    model_cost_usd: 0.5, judge_cost_usd: 0, total_tokens: 100, total_seconds: 10, working_seconds: 8, paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor", trajectory_url: null };
  const internet: Row[] = [base, { ...base, task_id: "concepts/b", status: "passed" }, { ...base, task_id: "building/c" }];
  const board = buildBoard(evals, [...internet, { ...base, mode: "skills" }, { ...base, mode: "skills", task_id: "building/c", status: "passed" }]);
  assert.deepEqual(board.lifts['["m","h",null]'], { overall: 50, concepts: 0, transactions: null, building: 100, security: null });
  assert.deepEqual(buildBoard(evals, internet).lifts['["m","h",null]'], { overall: null, concepts: null, transactions: null, building: null, security: null });
});
