import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Detail, Results } from "../app/board";
import { agentKey, buildBoard, scoreBoard, type Eval, type Row } from "../src/board";
import { existsSync } from "node:fs";
import path from "node:path";
import { siteRoot } from "../src/paths";
import { checkScoringSettings, scorings, type Scoring } from "../src/scoring";
import { taskScoring } from "../src/scoring-settings";

const agent = { model: "model-a", agent: "agent-a", effort: "high" };
const task = (id: string, pillar: Eval["pillar"] = "build"): Eval => ({
  id, hash: "h", instruction_hash: "h", environment_hash: "h", checks_hash: "h", title: id, pillar,
  description: "D.", instruction: "I.", modes: ["internet"],
});
const pass = { passed: true, reason: "Passed." }, fail = { passed: false, reason: "Failed." };
function row(task_id: string, checks: Row["checks"], overrides: Partial<Row> = {}): Row {
  return {
    schema_version: 8, task_id, task_hash: "h", instruction_hash: "h", environment_hash: "h", checks_hash: "h", skills_hash: null,
    ...agent, mode: "internet", trial: 1, status: Object.values(checks).every((check) => check.passed) ? "passed" : "failed",
    checks, error_kind: null, error_reason: null, total_tokens: 1, model_cost_usd: 1, judge_cost_usd: 0,
    paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor", total_seconds: 1, working_seconds: 1,
    trajectory_url: null, limit: null, ...overrides,
  };
}
// A real token-governor trial: everything passes except late votes.
const governorChecks = {
  compile: pass, test_snapshotCanRunIt: pass, test_quorumCountsTheWholeSupply: pass,
  test_theDelayGuardsTheMoney: pass, test_lateVotesExtendTheVote: fail,
};
const taskScores = (evals: Eval[], rows: Row[], scoring: Scoring) => {
  const board = scoreBoard(buildBoard(evals, rows), scoring);
  return Object.fromEntries(evals.map((evaluation) => [evaluation.id, board.tables.internet.pillars[evaluation.pillar].evals
    .find((entry) => entry.id === evaluation.id)!.cells[agentKey(agent)].score]));
};
const near = (actual: number | null, expected: number) => assert.ok(actual !== null && Math.abs(actual - expected) < 1e-9, `${actual} is not ${expected}`);

test("a token-governor trial scores 0, 0.8, 0 and 0.7, and 0.75 under Mix on a task flagged partial", () => {
  const evals = [task("build/token-governor"), task("build/swap-page")];
  const rows = [row("build/token-governor", governorChecks), row("build/swap-page", governorChecks)];
  const expected: Record<Scoring, number> = { "all-or-nothing": 0, partial: 0.8, mix: 0, weighted: 0.7 };
  for (const scoring of scorings) near(taskScores(evals, rows, scoring)["build/token-governor"], expected[scoring]);
  near(taskScores(evals, rows, "mix")["build/swap-page"], 0.75);
});

test("one-check tasks, no-answer rows and entry-only trials score the same under every version", () => {
  const evals = [task("concepts/one", "concepts"), task("concepts/two", "concepts"), task("build/entry-only")];
  const rows = [
    row("concepts/one", { answer: pass }), row("concepts/one", { answer: fail }, { trial: 2 }),
    row("concepts/two", { no_answer: { passed: false, reason: "No answer twice." } }),
    row("build/entry-only", { compile: pass }), row("build/entry-only", { compile: fail }, { trial: 2 }),
  ];
  for (const scoring of scorings) {
    assert.deepEqual(taskScores(evals, rows, scoring), { "concepts/one": 0.5, "concepts/two": 0, "build/entry-only": 0.5 }, scoring);
  }
});

test("unlisted tasks: Mix keeps them all or nothing unless they are audits, Weighted gives entry checks 0", () => {
  const checks = { report_written: pass, finding_a: pass, finding_b: fail };
  const evals = [task("build/audit-new"), task("build/unlisted"), task("concepts/q", "concepts")];
  const rows = [row("build/audit-new", checks), row("build/unlisted", checks), row("concepts/q", { answered: pass, target: fail })];
  assert.deepEqual(taskScores(evals, rows, "mix"), { "build/audit-new": 0.5, "build/unlisted": 0, "concepts/q": 0 });
  assert.deepEqual(taskScores(evals, rows, "weighted"), { "build/audit-new": 0.5, "build/unlisted": 0.5, "concepts/q": 0 });
  assert.deepEqual(taskScores(evals, rows, "partial"), { "build/audit-new": 2 / 3, "build/unlisted": 2 / 3, "concepts/q": 0.5 });
});

test("a task averages its scored trials, a pillar its tasks, Overall its pillars; cost per pass stays on passes", () => {
  const evals = [task("build/token-governor"), task("concepts/q", "concepts")];
  const rows = [
    row("build/token-governor", governorChecks),
    row("build/token-governor", { ...governorChecks, test_lateVotesExtendTheVote: pass }, { trial: 2 }),
    row("build/token-governor", {}, { trial: 3, status: "error", error_kind: "execution", error_reason: "Stopped." }),
    row("concepts/q", { target: fail }),
  ];
  const summary = scoreBoard(buildBoard(evals, rows), "weighted").tables.internet.summaries[agentKey(agent)];
  near(summary.scores.build!, 0.85);
  assert.equal(summary.scores.concepts, 0);
  near(summary.scores.overall!, 0.425);
  assert.equal(summary.costPerPass, 3);
});

test("the board shows the selected version, its explanation, and percents where passed/total would mislead", () => {
  const evals = [task("build/token-governor"), task("concepts/q", "concepts")];
  const rows = [row("build/token-governor", governorChecks), row("concepts/q", { target: pass })];
  const data = buildBoard(evals, rows);
  const render = (query: string) => renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams(query) }));
  const matrix = (html: string) => html.slice(html.indexOf('id="evals"'));

  for (const query of ["", "scoring=unknown"]) {
    const html = render(query);
    assert.match(html, /aria-checked="true"[^>]*>All or nothing<\/button>/);
    assert.ok(html.includes("This matches the live board.") && html.includes("Not the live board.") && html.includes("Trials passed per task."));
    assert.ok(matrix(html).includes(">0/1</button>") && matrix(html).includes(">1/1</button>"));
    assert.match(html, /href="\/compare\/?\?mode=internet"/);
  }
  const partial = render("scoring=partial");
  assert.match(partial, /aria-checked="true"[^>]*>Partial<\/button>/);
  assert.ok(partial.includes("scores 4 / 5 = 80%"), "The example line follows the version.");
  assert.ok(partial.includes("<code>report_written</code> (an audit report exists) count too"));
  assert.ok(partial.includes("Mean trial score per task.") && !partial.includes("Trials passed per task."), "The task matrix text follows the version.");
  assert.ok(partial.includes("agent-a / model-a. 90%. Open details."), "Overall averages Build 80% and Concepts 100%.");
  assert.ok(matrix(partial).includes(">80%</button>") && matrix(partial).includes(">1/1</button>"));
  assert.match(partial, /href="\/compare\/?\?mode=internet&amp;scoring=partial"/);
  assert.ok(render("scoring=weighted").includes("A trial scores points earned divided by points possible."));
});

test("the trial drawer shows the trial's score, and each check's points under Weighted", () => {
  const evaluation = { ...task("build/token-governor"), domain: "dapp-development" as const };
  const built = buildBoard([evaluation], [row("build/token-governor", governorChecks)]);
  const drawer = (scoring: Scoring) => renderToStaticMarkup(createElement(Detail, {
    data: scoreBoard(built, scoring), selection: { evaluation, agent, mode: "internet", run: 1 }, onSelect: () => {},
  }));
  assert.ok(!drawer("all-or-nothing").includes("<dt>Score</dt>") && !drawer("all-or-nothing").includes("point"));
  assert.ok(drawer("partial").includes("<dt>Score</dt><dd>80%</dd>") && !drawer("partial").includes("point"));
  const weighted = drawer("weighted");
  assert.ok(weighted.includes("<dt>Score</dt><dd>70%</dd>"));
  for (const [check, points] of [["compile", "0 points"], ["test_snapshotCanRunIt", "1 point"], ["test_lateVotesExtendTheVote", "3 points"]]) {
    assert.match(weighted, new RegExp(`<code>${check}</code><small class="check-points">${points}</small>`));
  }
});

test("scoring settings fail on a check no current row has, or a row check they do not list", () => {
  const governor = (checks: Row["checks"]) => [row("build/token-governor", checks)];
  assert.doesNotThrow(() => checkScoringSettings(governor(governorChecks)));
  assert.doesNotThrow(() => checkScoringSettings([...governor(governorChecks), row("build/token-governor", { no_answer: fail }, { trial: 2 })]));
  assert.doesNotThrow(() => checkScoringSettings([row("build/unlisted", { anything: pass })]));
  const missing = Object.fromEntries(Object.entries(governorChecks).filter(([check]) => check !== "test_lateVotesExtendTheVote"));
  assert.throws(() => checkScoringSettings(governor(missing)), /build\/token-governor.*test_lateVotesExtendTheVote/);
  assert.throws(() => checkScoringSettings(governor({ ...governorChecks, test_typo: pass })), /build\/token-governor.*test_typo/);
});

test("every task in the scoring settings is a task folder, so a misspelled id cannot fall back to the default rule", () => {
  for (const task of Object.keys(taskScoring)) assert.ok(existsSync(path.resolve(siteRoot, "../tasks", task, "task.toml")), `${task} is not a task.`);
});
