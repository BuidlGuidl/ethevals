import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Results } from "../app/board";
import Compare from "../app/compare/compare";
import { buildBoard, type Eval, type Row } from "../src/board";

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

test("the refusal toggle shows only for a mode with refused trials", () => {
  assert.match(page(""), /role="switch" aria-checked="false"[^>]*>.*Ignore refusals/);
  assert.match(page("refusals=ignore"), /role="switch" aria-checked="true"/);
  assert.doesNotMatch(page("mode=vanilla"), /Ignore refusals/);
  assert.doesNotMatch(leaderboard(page("mode=vanilla")), /refusal-info/);
});

test("refusal marks stay apart from unscored marks and say what is counted", () => {
  const html = page("");
  assert.match(leaderboard(html), /class="refusal-info" role="img" aria-label="1 refused trial scored as 0%\. Without refusals: 100\.0%, with 1 of 2 Build tasks scored\."/);
  assert.doesNotMatch(leaderboard(html), /unscored-info/);
  const matrix = html.split('class="matrix"')[1];
  assert.match(matrix, /class="refusal-info" role="img" aria-label="1 refused trial scored as 0%\."/);
  assert.match(page("refusals=ignore").split('class="matrix"')[1], />–<\/button>.*aria-label="1 refused trial ignored\. No scored trials left\."/s);
});

test("each prototype variant shows refusals its own way", () => {
  const b = leaderboard(page("variant=b")), c = page("variant=c&refusals=ignore");
  assert.match(b, /class="score-sub refusal-sub">.*1 refused<\/span>/);
  assert.doesNotMatch(b, /refusal-info/);
  assert.match(leaderboard(page("variant=b&refusals=ignore")), /1 ignored<\/span>/);
  assert.match(leaderboard(c), /class="score-sub">was 50% · 1\/2<\/span>/);
  assert.match(c, /class="refusal-strip">.*Ignoring 1 safety-refused trial across 1 agent\./);
  assert.doesNotMatch(page("variant=c"), /refusal-strip|was 50%/);
  assert.match(page("variant=b"), /Refusals.*Count as 0%.*Ignore/s);
});

test("Compare honors Ignore refusals and marks affected scores", () => {
  // Compare reads the URL in the browser; on the server it renders the default counted view.
  const html = renderToStaticMarkup(createElement(Compare, { data }));
  assert.match(html, /role="switch" aria-checked="false"/);
  assert.match(html, /class="refusal-info refusal-inline-mark" role="img" aria-label="1 refused trial scored as 0%\./);
});
