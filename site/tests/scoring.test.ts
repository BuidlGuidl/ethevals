import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Detail, Results } from "../app/board";
import { agentKey, buildBoard, scoreBoard, type Eval, type Row } from "../src/board";
import { checkCounts, scorings, trialScore } from "../src/scoring";
import type { TrialDisplay } from "../components/trial-display";

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
  const gated = render("scoring=gated&trial-display=b");
  assert.match(gated, /aria-checked="true"[^>]*>Gated<\/button>/);
  assert.match(gated, /Prototype · Trial display/);
  assert.match(gated, /All gates passed\. 3 of 4 counted checks passed\. Trial score 75%\./);
  assert.ok(/href="\/compare\/?\?mode=internet&amp;scoring=gated&amp;trial-display=b"/.test(gated));
});

test("the labels agree across the task cell, trial tile, and drawer", () => {
  const cases = [
    { evaluation: governor, checks: { ...governorChecks, test_lateVotesExtendTheVote: pass }, labels: ["passed", "passed 100%", "100%"] },
    { evaluation: governor, checks: governorChecks, labels: ["75%", "passed 75%", "75%"] },
    { evaluation: governor, checks: { ...governorChecks, test_snapshotCanRunIt: fail }, labels: ["50%", "passed 50%", "50%"] },
    { evaluation: governor, checks: gateFailure, labels: ["failed", "failed", "0%"] },
    { evaluation: audit, checks: auditChecks, labels: ["40%", "passed 40%", "2 of 5 found"] },
  ];
  const displays: TrialDisplay[] = ["a", "b", "c"];
  for (const { evaluation, checks, labels } of cases) {
    const data = buildBoard([evaluation], [row(evaluation.id, checks)]);
    for (const [index, display] of displays.entries()) {
      const board = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams(`scoring=gated&trial-display=${display}`) }));
      assert.ok(board.includes(`task score ${labels[index]}. Open details.`));
      const drawer = (run?: number) => renderToStaticMarkup(createElement(Detail, {
        data: scoreBoard(data, "gated"), selection: { evaluation: data.evaluations[evaluation.id], agent, mode: "internet", run },
        trialDisplay: display, onSelect: () => {},
      }));
      assert.ok(drawer().includes(`>${labels[index]}</span></td>`));
      assert.ok(drawer(1).includes(`>${labels[index]}</span></h1>`));
    }
  }
});

test("the trial tile names a missed check and the drawer shows each check's kind", () => {
  const data = scoreBoard(buildBoard([governor], [row(governor.id, governorChecks)]), "gated");
  const selection = { evaluation: data.evaluations[governor.id], agent, mode: "internet" as const };
  const taskView = renderToStaticMarkup(createElement(Detail, { data, selection, onSelect: () => {} }));
  assert.match(taskView, /title="Missed late votes extend the vote"/);
  const trialView = renderToStaticMarkup(createElement(Detail, { data, selection: { ...selection, run: 1 }, onSelect: () => {} }));
  assert.match(trialView, /Gates 3 of 3 · Judgment 1 of 2/);
  for (const [check, kind] of [["compile", "Gate · entry"], ["test_quorumCountsTheWholeSupply", "Gate"], ["test_lateVotesExtendTheVote", "Judgment check"]]) {
    assert.ok(trialView.includes(`<code>${check}</code><small class="check-kind">${kind}</small>`));
  }
});
