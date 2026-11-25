import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Detail, Results } from "../app/board";
import Compare from "../app/compare/compare";
import { taskHint } from "../components/trial-display";
import { agentKey, buildBoard, type Eval, type Row } from "../src/board";
import { scoreTrial } from "../src/scoring";

const agent = { model: "model-a", agent: "agent-a", effort: "high" };
const governor: Eval = {
  id: "build/token-governor", title: "Token governor", pillar: "build", hash: "h",
  instruction_hash: "h", environment_hash: "h", checks_hash: "h",
  description: "Check a governor build.", instruction: "Build a token governor.", modes: ["internet"],
  checks: { test_quorum: "gate", test_delay: "gate", snapshot: "judgment", late_votes: "judgment" },
};
const audit: Eval = { ...governor, id: "build/audit", checks: { finding_a: "judgment", finding_b: "judgment" } };
const concepts: Eval = { ...governor, id: "concepts/units", pillar: "concepts", checks: undefined };
const pass = { passed: true, reason: "Matches." }, fail = { passed: false, reason: "Differs." };
const mixed = { compile: pass, test_quorum: pass, test_delay: pass, snapshot: pass, late_votes: fail };
const full = { ...mixed, late_votes: pass };
const gateFailure = { ...full, test_quorum: fail };

function row(task: Eval, checks: Row["checks"], overrides: Partial<Row> = {}): Row {
  return {
    ...agent, schema_version: 8, task_id: task.id, task_hash: "h", instruction_hash: "h", environment_hash: "h",
    checks_hash: "h", skills_hash: null, mode: "internet", trial: 1, checks,
    status: Object.values(checks).every((check) => check.passed) ? "passed" : "failed",
    error_kind: null, error_reason: null, total_tokens: 0, model_cost_usd: 1, judge_cost_usd: 0,
    paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor",
    total_seconds: 1, working_seconds: 1, trajectory_url: null, limit: null,
    ...overrides,
  };
}

test("trial scores count gate and judgment checks after passing the entry and gate checks", () => {
  assert.deepEqual(scoreTrial(governor, row(governor, mixed)), { value: 0.75, passed: 3, total: 4, stop: null });
  assert.equal(scoreTrial(governor, row(governor, gateFailure)).value, 0);
  for (const name of ["compile", "answered", "no_answer", "report_written"]) {
    assert.equal(scoreTrial(governor, row(governor, { ...full, [name]: fail })).value, 0);
  }
  assert.equal(scoreTrial(audit, row(audit, { report_written: pass, finding_a: pass, finding_b: fail })).value, 0.5);
  assert.equal(scoreTrial(concepts, row(concepts, { answered: pass, answer: pass })).value, 1);
  assert.equal(scoreTrial(concepts, row(concepts, { answered: pass, answer: fail })).value, 0);
  assert.equal(scoreTrial(concepts, row(concepts, { answered: pass, answer: pass, second: fail })).value, 0);
  assert.equal(scoreTrial(concepts, row(concepts, { answered: pass, answer: pass, second: pass })).value, 1);
  assert.equal(scoreTrial(governor, row(governor, full, { status: "error" })).value, null);
});

test("the audit lookup check scores like an entry check: a fail scores 0 and a pass adds nothing", () => {
  const clean = { report_written: pass, no_audit_lookup: pass };
  assert.deepEqual(scoreTrial(audit, row(audit, { ...clean, finding_a: fail, finding_b: fail })),
    { value: 0, passed: 0, total: 2, stop: null });
  assert.equal(scoreTrial(audit, row(audit, { ...clean, finding_a: pass, finding_b: fail })).value, 0.5);
  const lookedUp = scoreTrial(audit, row(audit, { ...clean, no_audit_lookup: fail, finding_a: pass, finding_b: pass }));
  assert.deepEqual([lookedUp.value, lookedUp.value !== null && lookedUp.stop], [0, { kind: "entry", name: "no_audit_lookup" }]);
});

test("older rows use only tagged checks they carry and fall back to saved status when none count", () => {
  const score = (checks: Row["checks"], status: Row["status"] = "failed") =>
    scoreTrial(governor, row(governor, checks, { checks_hash: "old", status })).value;
  assert.equal(score({ old_gate: fail, test_quorum: pass, snapshot: fail, compile: pass }), 0.5);
  assert.equal(score({ old_gate: fail, snapshot: pass }), 1);
  assert.equal(score({ old_gate: pass, compile: pass }, "passed"), 1);
  assert.equal(score({ old_gate: fail }), 0);
  assert.equal(score({ old_gate: pass, compile: fail }, "passed"), 0);
});

test("task, pillar and Overall scores average their scored entries and cost per pass uses saved passes", () => {
  const rows = [row(governor, mixed), row(governor, full, { trial: 2 }),
    row(governor, full, { trial: 3, status: "error" }), row(audit, { finding_a: pass, finding_b: fail }),
    row(concepts, { answer: fail })];
  const table = buildBoard([governor, audit, concepts], rows).tables.internet;
  const key = agentKey(agent), summary = table.summaries[key];
  assert.equal(table.pillars.build.evals[0].cells[key].score, 0.875);
  assert.deepEqual(summary.scores, { overall: 0.34375, build: 0.6875, concepts: 0, act: null });
  assert.equal(summary.costPerPass, 4);
});

test("leaderboard, Compare and matrix use percentages and the matrix hint lists each trial", () => {
  const data = buildBoard([governor], [row(governor, mixed), row(governor, full, { trial: 2, status: "error" })], false, 2);
  const html = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams() }));
  assert.match(html, /aria-label="Overall, agent-a \/ model-a\. 75%\./);
  assert.match(html, /class="matrix-cell"[^>]*data-tone="leader"[^>]*>75%<\/button>/);
  assert.equal(taskHint(data.tables.internet.pillars.build.evals[0].cells[agentKey(agent)], { top: 88, tied: false }),
    "\u221213 pts · best 88%\nTrial 1 · 75% · 3 of 4 passed\nTrial 2 · Error");
  const comparison = renderToStaticMarkup(createElement(Compare, { data }));
  assert.equal((comparison.match(/>75%<\/span>/g) ?? []).length, 2);
});

const drawerFor = (task: Eval, trials: Row[]) => {
  const data = buildBoard([task], trials);
  return (view: "list" | "task" | number) => renderToStaticMarkup(createElement(Detail, {
    data, selection: { agent, mode: "internet", evaluation: view === "list" ? undefined : data.evaluations[task.id],
      run: typeof view === "number" ? view : undefined }, onSelect: () => {},
  }));
};

test("drawer uses all four trial dots, a percentage heading, and a dot-only score in the switcher", () => {
  const drawer = drawerFor(governor, [row(governor, full), row(governor, mixed, { trial: 2 }),
    row(governor, gateFailure, { trial: 3 }), row(governor, {}, { trial: 4, status: "error", error_reason: "Provider stopped." })]);
  const list = drawer("list"), table = drawer("task"), details = drawer(2);
  assert.match(list, /class="trial-legend".*100%.*Some checks missed.*0%.*Error/s);
  // Stops use the board's icons, so the error mark is the warning triangle, not a square.
  assert.match(list, /class="trial-legend".*data-state="error"[^>]*><svg[^>]*lucide-triangle-alert[^>]*>.*?<\/svg><\/span> Error/s);
  assert.match(list, /class="heat-chip"[^>]*><span>58%<\/span>/);
  assert.deepEqual([...list.split('class="run-dots"')[1].matchAll(/data-state="([^"]+)"/g)].map((match) => match[1]),
    ["full", "part", "zero", "error"]);
  assert.match(table, />100%<\/span>.*4 of 4 passed.*>75%<\/span>.*3 of 4 passed.*>0%<\/span>.*Gate check failed: quorum.*>Not scored<\/span>/s);
  assert.match(details, /Trial 2 of 4 <span class="trial-heading-score">75%<\/span><\/h1>/);
  const switcher = details.split('class="run-switcher"')[1].split("</div>")[0];
  assert.match(switcher, /Trial 2 <span class="run-dot" data-state="part" aria-hidden="true"><\/span><\/button>/);
  assert.doesNotMatch(switcher.replace(/<[^>]*>/g, ""), /%|Error/);
  const error = drawer(4);
  assert.match(error, /Not scored.*This trial ended in an error, so it is left out of the score\./s);
  assert.doesNotMatch(error, /Provider stopped|class="verifier-verdict"/);
});

test("check groups name their kinds, list failed checks first, and show the reason for a failed entry", () => {
  const details = drawerFor(governor, [row(governor, mixed)])(1);
  assert.match(details, /Gate checks <span>2 of 2<button[^>]*aria-label="Gate checks: Did the agent do what the instruction asked for\? Any failure sets the trial score to 0%\."/);
  assert.match(details, /Judgment checks <span>1 of 2<button[^>]*aria-label="Judgment checks: Did the agent make sound Ethereum decisions beyond the instruction\? Each check counts toward the trial score\."/);
  assert.match(details, /Judgment checks.*<code>late_votes<\/code><p>Differs\.<\/p>.*<code>snapshot<\/code><p>Matches\.<\/p>/s);
  assert.doesNotMatch(details, /<details|Passed \(/);
  assert.doesNotMatch(details, /<code>compile<\/code>|class="entry-check"/);
  for (const [name, label] of [["compile", "Did not compile"], ["answered", "No answer"],
    ["no_answer", "No answer"], ["report_written", "No report"]]) {
    const drawer = drawerFor(audit, [row(audit, { [name]: fail, finding_a: pass })]);
    assert.match(drawer("task"), new RegExp(`>0%<.*>${label}<`, "s"));
    assert.match(drawer(1), new RegExp(`<b>${label}</b><small>Differs\\.</small>.*Judgment checks`, "s"));
  }
  const findings = drawerFor(audit, [row(audit, { report_written: pass, finding_a: fail, finding_b: pass })])(1);
  assert.match(findings, /Judgment checks <span>1 of 2/);
  assert.doesNotMatch(findings, /Gate checks|report_written/);
  const old = drawerFor(governor, [row(governor, { ...full, old_gate: fail })])(1);
  assert.match(old, /Not counted <span>0 of 1<button[^>]*aria-label="Not counted: From an older version of this task&#x27;s checks\. It does not count toward the trial score\."/);
  assert.match(old, /<code>old_gate<\/code><p>Differs\.<\/p>/);
  assert.doesNotMatch(details, /Not counted/);
  const twoGates = drawerFor(governor, [row(governor, { ...full, test_quorum: fail, test_delay: fail })])("task");
  assert.match(twoGates, /Gate check failed: quorum and 1 more/);
  const answer = drawerFor(concepts, [row(concepts, { answered: pass, answer: fail })])(1);
  assert.match(answer, /<h3>Checks <span>0 of 1<\/span><\/h3>/);
  assert.doesNotMatch(answer, /info-hint|entry-check/);
});
