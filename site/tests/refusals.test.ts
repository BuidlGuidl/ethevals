import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Results } from "../app/board";
import Compare from "../app/compare/compare";
import { buildBoard, type Eval, type Row } from "../src/board";
import { TipBody, formulas } from "../components/scores";

const careful = { model: "careful", agent: "agent-a", effort: null }, steady = { model: "steady", agent: "agent-a", effort: null };
const task = (id: string): Eval => ({
  id: `build/${id}`, title: `Task ${id}`, pillar: "build", hash: "h", instruction_hash: "h", environment_hash: "h", checks_hash: "h",
  description: "Build it.", instruction: "Build it.", modes: ["internet", "vanilla"], checks: { finding_a: "judgment", finding_b: "judgment" },
});
const pass = { passed: true, reason: "Yes." }, fail = { passed: false, reason: "No." };
function row(evaluation: Eval, agent: Pick<Row, "model" | "agent" | "effort">, overrides: Partial<Row> = {}): Row {
  return {
    ...agent, schema_version: 8, task_id: evaluation.id, task_hash: "h", instruction_hash: "h", environment_hash: "h", checks_hash: "h",
    skills_hash: null, mode: "internet", trial: 1, status: "passed", checks: { finding_a: pass, finding_b: pass },
    error_kind: null, error_reason: null, total_tokens: 0, model_cost_usd: 1, judge_cost_usd: 0, paid_by: "api_key", judge: null,
    judge_paid_by: null, cost_source: "harbor", total_seconds: 1, working_seconds: 1, trajectory_url: null, limit: null, ...overrides,
  };
}
const refused: Partial<Row> = { status: "failed", checks: { no_answer: { passed: false, reason: "No answer twice." } },
  no_answer: [{ kind: "refused", stop_reason: "AgentSafetyRefusalError" }, { kind: "refused", stop_reason: "AgentSafetyRefusalError" }] };
const [a, b] = [task("a"), task("b")];
// careful refuses task b and scores 100% elsewhere; steady answers everything at 75%.
const data = buildBoard([a, b], [
  row(a, careful), row(b, careful, refused),
  row(a, steady, { status: "failed", checks: { finding_a: pass, finding_b: fail } }), row(b, steady),
  row(a, { ...careful, agent: null }, { mode: "vanilla" }),
]);
const page = (query: string) => renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams(query) }));
const leaderboard = (html: string) => html.split('class="leaderboard"')[1].split("</table>")[0];
const firstRow = (html: string) => leaderboard(html).split("<tbody>")[1].split("</tr>")[0];

test("Ignore refusals recomputes scores and re-sorts the leaderboard", () => {
  assert.match(firstRow(page("")), /steady/);
  assert.match(firstRow(page("")), /aria-label="Overall, agent-a \/ steady\. 75%\./);
  const ignored = page("refusals=ignore");
  assert.match(firstRow(ignored), /aria-label="Overall, agent-a \/ careful\. 100%\. 1 refused trial ignored\. 1 of 2 Build tasks scored\./);
});

test("with refusals ignored, affected scores show the counted score under them and a strip sits above the table", () => {
  const ignored = page("refusals=ignore");
  // Build was 50% with the refusal counted, and 1 of 2 Build tasks still has a score.
  assert.match(leaderboard(ignored), /class="score-sub">was 50% · 1\/2<\/span>/);
  // Overall spans pillars, so it shows the counted score alone.
  assert.match(leaderboard(ignored), /class="score-sub">was 50%<\/span>/);
  assert.match(ignored, /class="refusal-strip">.*Ignoring 1 safety-refused trial across 1 agent\./);
  assert.doesNotMatch(page(""), /refusal-strip|score-sub/);
});

test("the switch and its info icon end the toolbar, and stay while refusals are ignored", () => {
  const toolbar = (html: string) => html.split('class="toolbar"')[1].split('class="table-shell"')[0];
  assert.match(toolbar(page("")), /class="mode-note">.*role="switch" aria-checked="false"[^>]*>.*Ignore refusals<\/button>.*aria-label="Why ignore refusals: Some providers stop trials mid-task with a safety filter\. By default, refused trials score 0%\. Turn this on to leave refused trials out of the averages\."/s);
  assert.match(page("refusals=ignore"), /role="switch" aria-checked="true"/);
  // A mode with no refusals hides the switch, unless refusals are being ignored, so it can be turned off.
  assert.doesNotMatch(page("mode=vanilla"), /Ignore refusals/);
  assert.match(page("mode=vanilla&refusals=ignore"), /role="switch" aria-checked="true"/);
  assert.doesNotMatch(leaderboard(page("mode=vanilla")), /refusal-info/);
  assert.doesNotMatch(page(""), /variant/i);
});

test("refusal marks stay apart from unscored marks and say what is counted", () => {
  const html = page("");
  assert.match(leaderboard(html), /class="refusal-info" role="img" aria-label="1 refused trial \(scored as 0%\)\. Without refusals: 100\.0%\. 1 of 2 Build tasks scored\."/);
  assert.doesNotMatch(leaderboard(html), /unscored-info/);
  const matrix = html.split('class="matrix"')[1];
  assert.match(matrix, /class="refusal-info" role="img" aria-label="1 refused trial \(scored as 0%\)\."/);
  assert.match(page("refusals=ignore").split('class="matrix"')[1], />–<\/button>.*aria-label="1 refused trial ignored\. No scored trials left\."/s);
});

test("tooltips put each formula sentence on its own line and render refusal facts as bullets", () => {
  assert.equal(renderToStaticMarkup(createElement(TipBody, { text: formulas.pillar })),
    '<span class="tip-lines"><span>Pillar scores average task scores.</span><span>Tasks without a score are skipped.</span></span>');
  assert.equal(renderToStaticMarkup(createElement(TipBody, { bullets: ["1 refused trial (scored as 0%)", "Without refusals: 100.0%"] })),
    '<ul class="tip-bullets"><li>1 refused trial (scored as 0%)</li><li>Without refusals: 100.0%</li></ul>');
  assert.equal(renderToStaticMarkup(createElement(TipBody, { text: "Task score 50%\nTrial 1 · 0%" })),
    '<span class="tip-lines"><span>Task score 50%</span><span>Trial 1 · 0%</span></span>');
});

test("Compare honors Ignore refusals and marks affected scores", () => {
  // Compare reads the URL in the browser; on the server it renders the default counted view.
  const html = renderToStaticMarkup(createElement(Compare, { data }));
  assert.match(html, /class="toolbar">.*<p class="muted">.*role="switch" aria-checked="false"/s);
  assert.match(html, /class="refusal-info refusal-inline-mark" role="img" aria-label="1 refused trial \(scored as 0%\)\./);
});
