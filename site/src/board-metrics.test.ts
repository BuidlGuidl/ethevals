import assert from "node:assert/strict";
import test from "node:test";
import { buildBoard, costPerPass, skillLift, type Eval, type Row } from "./board";

const task = (id: string, pillar: Eval["pillar"]): Eval => ({ id, hash: "h", instruction_hash: "h", environment_hash: "h", checks_hash: "h",
  title: id, pillar, description: "", instruction: "", modes: ["internet", "skills"] });
const trial = (model: string, task_id: string, status: Row["status"]): Row => ({ schema_version: 8, task_id, task_hash: "h", instruction_hash: "h", environment_hash: "h", checks_hash: "h",
  skills_hash: null, model, agent: "h", effort: null, mode: "internet", trial: 1, status, checks: {}, error_kind: null, error_reason: null, limit: null,
  model_cost_usd: 0, judge_cost_usd: 0, total_tokens: 1, total_seconds: 1, working_seconds: 1, paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor", trajectory_url: null });
const tasks = (pillar: Eval["pillar"], count: number) => Array.from({ length: count }, (_, index) => task(`${pillar}/${index}`, pillar));
const overall = (evals: Eval[], rows: Row[], model = "m") => buildBoard(evals, rows).tables.internet.summaries[JSON.stringify([model, "h", null])].scores.overall;
// Every task in a pillar gets the same status, so the pillar score is 100% for passed and 0% for failed.
const run = (evals: Eval[], status: Partial<Record<Eval["pillar"], Row["status"]>>, model = "m") =>
  evals.filter((evaluation) => status[evaluation.pillar]).map((evaluation) => trial(model, evaluation.id, status[evaluation.pillar]!));

test("Overall counts each pillar by its number of tasks: Act's 3 tasks weigh 3 of 53", () => {
  const evals = [...tasks("concepts", 25), ...tasks("build", 25), ...tasks("act", 3)];
  assert.equal(overall(evals, run(evals, { concepts: "passed", build: "failed", act: "passed" })), 28 / 53);
  assert.equal(overall(evals, run(evals, { concepts: "failed", build: "failed", act: "passed" })), 3 / 53);
});

test("Overall caps each pillar at 25 tasks, so 50/25/25 tasks give equal thirds", () => {
  const evals = [...tasks("concepts", 50), ...tasks("build", 25), ...tasks("act", 25)];
  assert.equal(overall(evals, run(evals, { concepts: "passed", build: "failed", act: "failed" })), 1 / 3);
  assert.equal(overall(evals, run(evals, { concepts: "failed", build: "passed", act: "passed" })), 2 / 3);
});

test("Overall skips a pillar without a score", () => {
  const evals = [...tasks("concepts", 25), ...tasks("build", 3), ...tasks("act", 3)];
  assert.equal(overall(evals, run(evals, { concepts: "passed", build: "failed" })), 25 / 28);
  assert.equal(overall(evals, evals.map((evaluation) => trial("m", evaluation.id, "error"))), null);
});

test("Overall weights come from the task list, not from the tasks a configuration scored", () => {
  const evals = [...tasks("concepts", 25), ...tasks("act", 3)];
  const errored = evals.filter((evaluation) => evaluation.pillar === "concepts").map((evaluation, index) =>
    trial("partial", evaluation.id, index === 0 ? "passed" : "error"));
  const rows = [...run(evals, { concepts: "passed", act: "failed" }), ...errored, ...run(evals, { act: "failed" }, "partial")];
  assert.equal(overall(evals, rows, "m"), 25 / 28);
  assert.equal(overall(evals, rows, "partial"), 25 / 28);
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
    { id: "concepts/a", hash: "a", instruction_hash: "a", environment_hash: "a", checks_hash: "a", title: "A", pillar: "concepts", description: "Check A.", instruction: "A?", modes: ["internet", "skills"] },
    { id: "build/b", hash: "b", instruction_hash: "b", environment_hash: "b", checks_hash: "b", title: "B", pillar: "build", description: "Check B.", instruction: "B?", modes: ["internet", "skills"] },
  ];
  const base: Row = { schema_version: 8, task_id: "concepts/a", task_hash: "a", instruction_hash: "a", environment_hash: "a", checks_hash: "a", skills_hash: null, model: "m", agent: "h", effort: null,
    mode: "internet", trial: 1, status: "passed", checks: {}, error_kind: null, error_reason: null, limit: null,
    model_cost_usd: 0.5, judge_cost_usd: 90, total_tokens: 100, total_seconds: 10, working_seconds: 8, paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor", trajectory_url: null };
  const board = buildBoard(evals, [base, { ...base, task_id: "build/b", task_hash: "b", instruction_hash: "b", environment_hash: "b", checks_hash: "b", status: "failed" },
    { ...base, mode: "skills", skills_hash: "pack" }, { ...base, mode: "skills", skills_hash: "pack", task_id: "build/b", task_hash: "b", instruction_hash: "b", environment_hash: "b", checks_hash: "b" }]);
  assert.deepEqual(board.tables.internet.summaries['["m","h",null]'], {
    scores: { overall: 0.5, concepts: 1, act: null, build: 0 },
    costPerPass: 1, medianTokens: 100, passed: 1, total: 2, errors: 0, missing: 0,
  });
  assert.deepEqual(board.lifts['["m","h",null]'], { overall: 50, concepts: 0, act: null, build: 100 });
  assert.deepEqual(board.counts, { evals: 2, agents: 1, runs: 4 });
});

test("lift pairs tasks when skills covers a strict subset of Internet results", () => {
  const evaluation: Eval = { id: "concepts/a", hash: "a", instruction_hash: "a", environment_hash: "a", checks_hash: "a", title: "A", pillar: "concepts", description: "Check A.", instruction: "A?", modes: ["internet", "skills"] };
  const evals: Eval[] = [evaluation, { ...evaluation, id: "concepts/b" }, { ...evaluation, id: "build/c", pillar: "build" }];
  const base: Row = { schema_version: 8, task_id: "concepts/a", task_hash: "a", instruction_hash: "a", environment_hash: "a", checks_hash: "a", skills_hash: null, model: "m", agent: "h", effort: null,
    mode: "internet", trial: 1, status: "failed", checks: {}, error_kind: null, error_reason: null, limit: null,
    model_cost_usd: 0.5, judge_cost_usd: 0, total_tokens: 100, total_seconds: 10, working_seconds: 8, paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor", trajectory_url: null };
  const internet: Row[] = [base, { ...base, task_id: "concepts/b", status: "passed" }, { ...base, task_id: "build/c" }];
  const board = buildBoard(evals, [...internet, { ...base, mode: "skills" }, { ...base, mode: "skills", task_id: "build/c", status: "passed" }]);
  assert.deepEqual(board.lifts['["m","h",null]'], { overall: 100 / 3, concepts: 0, act: null, build: 100 });
  assert.deepEqual(buildBoard(evals, internet).lifts['["m","h",null]'], { overall: null, concepts: null, act: null, build: null });
});
