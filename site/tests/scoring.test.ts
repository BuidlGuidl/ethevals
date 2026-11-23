import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Detail, Results } from "../app/board";
import { agentKey, buildBoard, scoreBoard, type Eval, type Row } from "../src/board";
import { checkCounts, scorings, trialScore } from "../src/scoring";

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
const governor = task("build/token-governor");
const audit = task("build/audit-example");
const concepts = task("concepts/answer", "concepts");
const gateFailure = { ...governorChecks, test_quorumCountsTheWholeSupply: fail, test_lateVotesExtendTheVote: pass };
const auditChecks = { report_written: pass, finding_a: pass, finding_b: pass, finding_c: fail, finding_d: fail, finding_e: fail };
const error = row(governor.id, {}, { trial: 3, status: "error", error_kind: "execution", error_reason: "Stopped." });

test("the token-governor trial counts both gates and one judgment check", () => {
  const trial = row(governor.id, governorChecks);
  assert.equal(trialScore(governor.id, trial, "all-or-nothing"), 0);
  assert.equal(trialScore(governor.id, trial, "gated"), 0.75);
  assert.deepEqual(checkCounts(governor.id, trial.checks), {
    gates: { passed: 3, total: 3 },
    judgment: { passed: 1, total: 2 },
    counted: { passed: 3, total: 4 },
  });
});

test("any failed gate sets the trial score to zero", () => {
  for (const checks of [gateFailure, { ...governorChecks, compile: fail }, { ...auditChecks, report_written: fail }]) {
    const evaluation = "report_written" in checks ? audit : governor;
    assert.equal(trialScore(evaluation.id, row(evaluation.id, checks), "gated"), 0);
  }
});

test("the audit counts each finding after its report gate passes", () => {
  const trial = row(audit.id, auditChecks);
  assert.deepEqual(checkCounts(audit.id, trial.checks).gates, { passed: 1, total: 1 });
  assert.equal(trialScore(audit.id, trial, "gated"), 0.4);
  assert.equal(trialScore(audit.id, trial, "all-or-nothing"), 0);
});

test("a Concepts answer scores 100% or 0% under either rule", () => {
  for (const scoring of scorings) {
    assert.equal(trialScore(concepts.id, row(concepts.id, { answered: pass, target: pass }), scoring), 1);
    assert.equal(trialScore(concepts.id, row(concepts.id, { answered: pass, target: fail }), scoring), 0);
    assert.equal(trialScore(concepts.id, row(concepts.id, { no_answer: fail }), scoring), 0);
  }
});

test("errors stay out of scores and each roll-up averages its scored entries", () => {
  const rows = [
    row(governor.id, governorChecks),
    row(governor.id, { ...governorChecks, test_lateVotesExtendTheVote: pass }, { trial: 2 }),
    error,
    row(audit.id, auditChecks),
    row(concepts.id, { target: fail }),
  ];
  for (const scoring of scorings) assert.equal(trialScore(governor.id, error, scoring), null);
  const table = scoreBoard(buildBoard([governor, audit, concepts], rows), "gated").tables.internet;
  assert.equal(table.pillars.build.evals[0].cells[agentKey(agent)].score, 0.875);
  const summary = table.summaries[agentKey(agent)];
  assert.equal(summary.scores.build, (0.875 + 0.4) / 2);
  assert.equal(summary.scores.concepts, 0);
  assert.equal(summary.scores.overall, (0.875 + 0.4) / 4);
  assert.equal(summary.errors, 1);
  assert.equal(summary.costPerPass, 4);
});

test("the board keeps its default and explains Gated with the counted checks", () => {
  const data = buildBoard([governor], [row(governor.id, governorChecks)]);
  const render = (query: string) => renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams(query) }));
  for (const query of ["", "scoring=unknown"]) {
    const html = render(query);
    assert.match(html, /aria-checked="true"[^>]*>All or nothing<\/button>/);
    assert.match(html, />0\/1<\/button>/);
  }
  const gated = render("scoring=gated&trial-display=numbers");
  assert.match(gated, /aria-checked="true"[^>]*>Gated<\/button>/);
  assert.match(gated, /<option value="marks">Marks<\/option><option value="numbers" selected="">Numbers<\/option>/);
  assert.match(gated, /All gate checks passed\. 3 of 4 counted checks passed\. Trial score 75%\./);
  assert.match(gated, /href="\/compare\/?\?mode=internet&amp;scoring=gated&amp;trial-display=numbers"/);
  assert.match(gated, /aria-label="[^"]*task score 75%\. Open details\."[^>]*>75%<\/button>/);
});

test("the matrix, drawer list, trials table, switcher, and heading show the same mark", () => {
  const cases = [
    { evaluation: governor, trial: row(governor.id, { ...governorChecks, test_lateVotesExtendTheVote: pass }), mark: "score", fill: "100%", heading: "100%", hint: "4 of 4 checks" },
    { evaluation: governor, trial: row(governor.id, governorChecks), mark: "score", fill: "75%", heading: "75%", hint: "3 of 4 checks · missed late votes extend the vote" },
    { evaluation: governor, trial: row(governor.id, { ...governorChecks, test_snapshotCanRunIt: fail }), mark: "score", fill: "50%", heading: "50%", hint: "2 of 4 checks" },
    { evaluation: governor, trial: row(governor.id, gateFailure), mark: "gate-check", heading: "0%", hint: "A gate check failed: quorum counts the whole supply" },
    { evaluation: audit, trial: row(audit.id, auditChecks), mark: "score", fill: "40%", heading: "40%", hint: "Found 2 of 5" },
    { evaluation: governor, trial: error, mark: "error", heading: "Error", hint: "Error" },
    { evaluation: concepts, trial: row(concepts.id, { answered: pass, target: fail }), mark: "score", fill: "0%", heading: "0%", hint: "0 of 1 checks · missed target" },
  ];
  for (const { evaluation, trial, mark, fill, heading, hint } of cases) {
    const data = buildBoard([evaluation], [trial]);
    const board = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams("scoring=gated") }));
    const drawer = (selection: { evaluation?: Eval; run?: number }) => renderToStaticMarkup(createElement(Detail, {
      data: scoreBoard(data, "gated"),
      selection: { evaluation: selection.evaluation && data.evaluations[evaluation.id], agent, mode: "internet", run: selection.run },
      onSelect: () => {},
    }));
    const detail = drawer({ evaluation, run: trial.trial });
    const matrixCell = board.match(/<button class="matrix-cell" data-marks="true"[^>]*>(.*?)<\/button>/s);
    assert.ok(matrixCell, hint);
    const runHeading = detail.match(/<h1[^>]*class="run-heading">(.*?)<\/h1>/s)?.[1];
    const taskList = drawer({});
    const trialsTable = drawer({ evaluation });
    for (const html of [matrixCell[1], taskList, trialsTable, runHeading, detail.split('class="run-switcher"')[1]]) {
      assert.ok(html, hint);
      assert.ok(html.includes(`data-mark="${mark}"`), hint);
      if (fill) assert.ok(html.includes(`style="--score:${fill}"`), hint);
      assert.ok(html.includes(`title="Trial ${trial.trial} · ${hint}`), hint);
    }
    assert.match(matrixCell[1].replace(/<[^>]*>/g, ""), /^$/);
    assert.ok(runHeading?.includes(`>${heading}</span>`));
  }
});

test("task marks sort by score, then gate checks and errors", () => {
  const rows = [
    error,
    row(governor.id, gateFailure, { trial: 1 }),
    row(governor.id, { ...governorChecks, test_lateVotesExtendTheVote: pass }, { trial: 4 }),
    row(governor.id, governorChecks, { trial: 2 }),
  ];
  const html = renderToStaticMarkup(createElement(Results, {
    data: buildBoard([governor], rows), query: new URLSearchParams("scoring=gated"),
  }));
  const cell = html.match(/<button class="matrix-cell" data-marks="true".*?<\/button>/s)?.[0];
  assert.ok(cell);
  assert.match(cell, /title="Task score 58%\nTrial 4[^\n]+\nTrial 2[^\n]+\nTrial 1[^\n]+\nTrial 3 · Error"/);
  assert.deepEqual([...cell.matchAll(/data-mark="([^"]+)"/g)].map((match) => match[1]), ["score", "score", "gate-check", "error"]);
});

test("entry checks sit in the gate group and reasons for failed checks stay visible", () => {
  const data = scoreBoard(buildBoard([governor], [row(governor.id, governorChecks)]), "gated");
  const selection = { evaluation: data.evaluations[governor.id], agent, mode: "internet" as const };
  const trialView = renderToStaticMarkup(createElement(Detail, { data, selection: { ...selection, run: 1 }, onSelect: () => {} }));
  assert.match(trialView, /Gate checks <span>3 of 3<\/span>.*?<details><summary>Passed \(3\)<\/summary>.*?<code>compile<\/code>/);
  assert.match(trialView, /Judgment checks <span>1 of 2<\/span>.*?<code>test_lateVotesExtendTheVote<\/code><p>Failed\.<\/p>.*?<details><summary>Passed \(1\)<\/summary>.*?<code>test_snapshotCanRunIt<\/code>/);
});
