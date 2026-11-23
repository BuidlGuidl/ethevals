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
  const gated = render("scoring=gated");
  assert.match(gated, /aria-checked="true"[^>]*>Gated<\/button>/);
  assert.match(gated, /All gate checks passed\. 3 of 4 counted checks passed\. Trial score 75%\./);
  assert.match(gated, /href="\/compare\/?\?mode=internet&amp;scoring=gated"/);
  assert.match(gated, /aria-label="[^"]*task score 75%\. Open details\."[^>]*>75%<\/button>/);
});

const drawerFor = (evaluation: Eval, rows: Row[]) => {
  const data = scoreBoard(buildBoard([evaluation], rows), "gated");
  return (selection: { evaluation?: Eval; run?: number }) => renderToStaticMarkup(createElement(Detail, {
    data, selection: { evaluation: selection.evaluation && data.evaluations[evaluation.id], agent, mode: "internet", run: selection.run },
    onSelect: () => {},
  }));
};

test("every level shows a trial as a percentage, with one dot and the reason in words", () => {
  const cases = [
    { evaluation: governor, trial: row(governor.id, { ...governorChecks, test_lateVotesExtendTheVote: pass }), state: "full", score: "100%", note: "4 of 4 passed" },
    { evaluation: governor, trial: row(governor.id, governorChecks), state: "part", score: "75%", note: "3 of 4 passed" },
    { evaluation: governor, trial: row(governor.id, gateFailure), state: "zero", score: "0%", note: "Gate check failed: quorum counts the whole supply" },
    { evaluation: governor, trial: row(governor.id, { ...governorChecks, compile: fail }), state: "zero", score: "0%", note: "Did not compile" },
    { evaluation: audit, trial: row(audit.id, auditChecks), state: "part", score: "40%", note: "2 of 5 passed" },
    { evaluation: audit, trial: row(audit.id, { no_answer: fail }), state: "zero", score: "0%", note: "No answer" },
    { evaluation: governor, trial: error, state: "error", score: "Error", note: "Error" },
    { evaluation: concepts, trial: row(concepts.id, { answered: pass, target: fail }), state: "zero", score: "0%", note: "0 of 1 passed" },
  ];
  for (const { evaluation, trial, state, score, note } of cases) {
    const drawer = drawerFor(evaluation, [trial]);
    const dot = `<span class="run-dot" data-state="${state}" aria-hidden="true"></span>`;
    const hint = `Trial ${trial.trial} · ${score === "Error" ? "" : `${score} · `}${note}`;
    const taskList = drawer({}), trialsTable = drawer({ evaluation }), detail = drawer({ evaluation, run: trial.trial });
    assert.ok(taskList.includes(dot), note);
    assert.ok(taskList.includes(`\n${hint}"`), note);
    if (score !== "Error") assert.match(taskList, new RegExp(`class="heat-chip"[^>]*>${score}<`), note);
    assert.ok(trialsTable.includes(`${dot}<span>${score}</span>`), note);
    assert.ok(trialsTable.includes(`>${note}</span></td>`), note);
    const heading = detail.match(/<h1[^>]*class="run-heading">(.*?)<\/h1>/s)?.[1];
    assert.ok(heading?.includes(`<span class="trial-heading-score">${score}</span>`), note);
    assert.ok(!heading?.includes("run-dot"), note);
    const switcher = detail.split('class="run-switcher"')[1].split("</div>")[0];
    assert.ok(switcher.includes(dot), note);
    assert.doesNotMatch(switcher.replace(/<[^>]*>/g, ""), /%|Error/, note);
    assert.doesNotMatch(taskList + trialsTable + detail, / found/);
  }
});

test("a matrix cell is the task score and its hint lists each trial", () => {
  const rows = [
    row(governor.id, gateFailure, { trial: 1 }),
    row(governor.id, governorChecks, { trial: 2 }),
    error,
  ];
  const data = buildBoard([governor], rows);
  const html = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams("scoring=gated") }));
  assert.match(html, /<button class="matrix-cell"[^>]*>38%<\/button>/);
  const list = drawerFor(governor, rows)({});
  assert.match(list, /title="Task score 38%\nTrial 1 · 0% · Gate check failed: quorum counts the whole supply\nTrial 2 · 75% · 3 of 4 passed\nTrial 3 · Error"/);
  assert.deepEqual([...list.matchAll(/class="eval-list-row".*?<\/button>/gs)].flatMap((match) =>
    [...match[0].matchAll(/data-state="([^"]+)"/g)].map((state) => state[1])), ["zero", "part", "error"]);
});

test("the trial view hides a passed hand-in check and names a failed one", () => {
  const trialView = drawerFor(governor, [row(governor.id, governorChecks)])({ evaluation: governor, run: 1 });
  assert.match(trialView, /<dt>Checks<\/dt><dd>3 of 4<\/dd>/);
  assert.doesNotMatch(trialView, /entry-check|Compiled/);
  assert.match(trialView, /Gate checks <span>2 of 2<button type="button" class="info-hint" aria-label="Gate checks: Did the agent do what the instruction asked for\? Any failure sets the trial score to 0%\."/);
  assert.doesNotMatch(trialView, /<p[^>]*>Did the agent/);
  assert.match(trialView, /Judgment checks <span>1 of 2<button.*?<\/span>.*?<code>test_lateVotesExtendTheVote<\/code><p>Failed\.<\/p>.*?<details><summary>Passed \(1\)<\/summary>.*?<code>test_snapshotCanRunIt<\/code>/s);
  assert.doesNotMatch(trialView, /<code>compile<\/code>/);

  const auditView = drawerFor(audit, [row(audit.id, auditChecks)])({ evaluation: audit, run: 1 });
  assert.match(auditView, /Judgment checks <span>2 of 5<button/);
  assert.doesNotMatch(auditView, /Gate checks|Known findings|Report written|entry-check/);

  const noAnswer = drawerFor(audit, [row(audit.id, { no_answer: { passed: false, reason: "No answer twice." } })])({ evaluation: audit, run: 1 });
  assert.match(noAnswer, /<b>No answer<\/b><small>No answer twice\.<\/small>/);
  assert.doesNotMatch(noAnswer, /Judgment checks/);

  const conceptsView = drawerFor(concepts, [row(concepts.id, { answered: pass, target: fail })])({ evaluation: concepts, run: 1 });
  assert.match(conceptsView, /<h4>Checks <span>0 of 1<\/span><\/h4>/);
  assert.doesNotMatch(conceptsView, /info-hint/);
});
