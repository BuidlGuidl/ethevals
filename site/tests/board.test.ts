import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Board, { Detail, Results } from "../app/board";
import { buildBoard, agentKey, type Eval, type DisplayEval, type Row, type Agent } from "../src/board";
import { currentRows, loadBoard, parseRows } from "../src/load";
import { decodeSelection, encodeSelection, type Selection } from "../src/selection";
import { ignoreRefusals } from "../src/refusals";
import { Configuration } from "../components/configuration";
import { money, peers } from "../components/scores";
import { taskHint } from "../components/trial-display";

const evaluation: Eval & Pick<DisplayEval, "domain"> = {
  id: "concepts/units", hash: "current", instruction_hash: "current", environment_hash: "current", checks_hash: "current", title: "Units", pillar: "concepts",
  domain: "dapp-development",
  description: "Check units.", instruction: "How many wei equal one ether?", modes: ["internet", "vanilla"],
};
const agent = { model: "model-a", agent: "agent-a", effort: "high" };
function row(overrides: Partial<Row> = {}): Row {
  return {
    schema_version: 8, task_id: "concepts/units", task_hash: "current", instruction_hash: "current", environment_hash: "current", checks_hash: "current", skills_hash: null,
    ...agent, mode: "internet", trial: 1, status: "passed",
    checks: { answer: { passed: true, reason: "The answer matches." } }, error_kind: null, error_reason: null,
    total_tokens: 100, model_cost_usd: 0.2, judge_cost_usd: 0.05,
    paid_by: "api_key", judge: null, judge_paid_by: null, cost_source: "harbor", total_seconds: 8, working_seconds: 7,
    trajectory_url: null, limit: null, ...overrides,
  };
}

// The text a reader sees on the first label's cost and token line, and on each drawer task list row.
const strip = (html: string) => html.replace(/<[^>]*>/g, "");
const spend = (html: string) => { const line = html.match(/class="configuration">[\s\S]*?<\/small><small>([\s\S]*?)<\/small>/)?.[1]; return line === undefined ? undefined : strip(line); };
const taskSpends = (html: string) => [...html.matchAll(/class="task-cost">((?:<span[^>]*>[^<]*<\/span>|[^<])*)<\/span>/g)].map((match) => strip(match[1]));

function getCell(evaluation: Eval, agent: Agent, mode: "internet" | "vanilla", rows: Row[]) {
  return buildBoard([evaluation], rows).tables[mode].pillars[evaluation.pillar].evals[0].cells[agentKey(agent)];
}

test("the drawer labels the full Harbor Hub trial and the release fallback", () => {
  for (const [url, label] of [
    ["https://hub.harborframework.com/jobs/job-id/trials/trial-id", "Open full trial on Harbor Hub ↗"],
    ["https://github.com/owner/repo/releases/download/results-1/trajectory.json", "Open trajectory ↗"],
  ]) {
    const data = buildBoard([evaluation], [row({ trajectory_url: url })]);
    const panel = renderToStaticMarkup(createElement(Detail, {
      data, selection: { evaluation, pillar: "concepts", agent, mode: "internet", run: 1 },
      onSelect: () => {},
    }));
    assert.ok(panel.includes(`href="${url}" target="_blank" rel="noreferrer">${label}</a>`));
  }
});

const failure = { status: "failed", checks: { answer: { passed: false, reason: "The answer differs." } } } as const;

const noAnswerTwice = (kind: "refused" | "empty"): Partial<Row> => ({ status: "failed", checks: { no_answer: { passed: false, reason: "No answer twice." } },
  no_answer: [{ kind, stop_reason: "stop" }, { kind, stop_reason: "stop" }] });

test("the drawer names a safety refusal or an empty reply after two no-answer tries", () => {
  for (const [kind, label] of [["refused", /class="refusal-note">.*Safety refusal on both tries, so this trial scores 0%\./], ["empty", /<p class="negative">Empty reply<\/p>/]] as const) {
    const data = buildBoard([evaluation], [row(noAnswerTwice(kind))]);
    const panel = renderToStaticMarkup(createElement(Detail, {
      data, selection: { evaluation, pillar: "concepts", agent, mode: "internet", run: 1 }, onSelect: () => {},
    }));
    assert.match(panel, label);
    assert.equal(data.tables.internet.summaries[agentKey(agent)].total, 1);
  }
});

test("refused trials get their own label and dot, and say when they are ignored", () => {
  const rows = [row(noAnswerTwice("refused")), row({ trial: 2 })];
  const task = (data: ReturnType<typeof buildBoard>) => renderToStaticMarkup(createElement(Detail, {
    data, selection: { evaluation, agent, mode: "internet" }, onSelect: () => {} }));
  const counted = task(buildBoard([evaluation], rows));
  assert.match(counted, /data-state="refused"[^>]*><svg[^>]*lucide-shield-ban[^>]*>.*?<\/svg><\/span>0%<\/span><\/td><td class="refusal-text">Safety refusal<\/td>/);
  const ignored = task(ignoreRefusals(buildBoard([evaluation], rows)));
  assert.match(ignored, /data-state="refused" data-ignored="true"[^>]*><svg[^>]*lucide-shield-ban[^>]*>.*?<\/svg><\/span>Ignored<\/span><\/td><td class="refusal-text">Refused<\/td>/);
  assert.doesNotMatch(task(buildBoard([evaluation], [row({ trial: 2 })])), /refusal|data-state="refused"/);
});

test("only the Overall and pillar drawers carry the refusal banner; the task drawer's rows say it", () => {
  const rows = [row(noAnswerTwice("refused")), row({ trial: 2 })];
  const drawer = (data: ReturnType<typeof buildBoard>, selection: Selection) =>
    renderToStaticMarkup(createElement(Detail, { data, selection, onSelect: () => {} }));
  for (const [data, banner] of [[buildBoard([evaluation], rows), "1 refused trial (scored as 0%)."],
    [ignoreRefusals(buildBoard([evaluation], rows)), "1 refused trial ignored."]] as const) {
    for (const selection of [{ agent, mode: "internet" }, { agent, mode: "internet", pillar: "concepts" }] as Selection[])
      assert.match(drawer(data, selection), new RegExp(`class="refusal-banner">.*${banner.replace(/[().]/g, "\\$&")}`));
    const task = drawer(data, { evaluation, agent, mode: "internet" });
    assert.doesNotMatch(task, /refusal-banner/);
    assert.match(task, /class="refusal-text">(Safety refusal|Refused)<\/td>/);
  }
});

test("a refused trial view gives the refusal note without repeating it as a no-answer check", () => {
  const view = (data: ReturnType<typeof buildBoard>) => renderToStaticMarkup(createElement(Detail, {
    data, selection: { evaluation, agent, mode: "internet", run: 1 }, onSelect: () => {} }));
  const refused = buildBoard([evaluation], [row(noAnswerTwice("refused"))]);
  for (const data of [refused, ignoreRefusals(refused)]) {
    const html = view(data);
    assert.match(html, /class="refusal-note">/);
    assert.doesNotMatch(html, /class="entry-check"|No answer twice\.|No checks counted/);
  }
  // An empty reply is not a refusal, so its no-answer check stays listed.
  assert.match(view(buildBoard([evaluation], [row(noAnswerTwice("empty"))])), /class="entry-check">.*<b>No answer<\/b><small>No answer twice\.<\/small>/);
});

test("a trial answered on retry after a refusal keeps its score and says so in its trial view", () => {
  const data = buildBoard([evaluation], [row({ no_answer: [{ kind: "refused", stop_reason: "stop" }] })]);
  const view = renderToStaticMarkup(createElement(Detail, {
    data, selection: { evaluation, agent, mode: "internet", run: 1 }, onSelect: () => {} }));
  assert.match(view, /Answered on retry after 1 safety refusal\./);
  assert.doesNotMatch(view, /refusal-note|refusal-banner/);
});

const error = { status: "error", checks: {}, error_kind: "execution", error_reason: "Sandbox stopped." } as const;

test("a Concepts task score averages its trial scores and excludes errors", () => {
  const cell = getCell(evaluation, agent, "internet", [row(), row({ trial: 2 }), row({ trial: 3, ...failure }), row({ trial: 4, ...error })]);
  assert.deepEqual({ state: cell.state, score: cell.score, passed: cell.passed, total: cell.total, errors: cell.errors },
    { state: "score", score: 2 / 3, passed: 2, total: 3, errors: 1 });
  assert.equal(cell.trials[3].score.value, null);
  assert.equal(cell.trials[3].issue, "");
});

test("planned trials without a score are counted and marked on the board", () => {
  const tasks: Eval[] = [evaluation, { ...evaluation, id: "build/token", title: "Token", pillar: "build" },
    { ...evaluation, id: "build/page", title: "Page", pillar: "build" }, { ...evaluation, id: "act/swap", title: "Swap", pillar: "act", modes: ["vanilla"] }];
  const data = buildBoard(tasks, [row(), row({ trial: 2, ...failure }),
    row({ task_id: "build/token" }), row({ task_id: "build/token", trial: 2, ...error })], false, 2);
  const table = data.tables.internet, key = agentKey(agent);
  const cells = (pillar: "concepts" | "build" | "act") => table.pillars[pillar].evals.map((entry) => entry.cells[key].missing);
  // An error and a trial that never ran both count. A mode the task does not declare plans nothing.
  assert.deepEqual([cells("concepts"), cells("build"), cells("act")], [[0], [1, 2], [0]]);
  assert.deepEqual([table.pillars.concepts.cells[key].missing, table.pillars.build.cells[key].missing, table.summaries[key].missing], [0, 3, 3]);
  assert.equal(buildBoard(tasks, [row()]).tables.internet.summaries[key].missing, 0);
  const page = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams() }));
  // Overall, Build, and the one scored Build task carry the icon. The unrun task keeps its dash.
  assert.deepEqual([...page.matchAll(/class="unscored-info" role="img" aria-label="([^"]+)"/g)].map((match) => match[1]),
    ["3 trials have no score yet.", "3 trials have no score yet.", "1 trial has no score yet."]);
  assert.ok(page.includes('title="No trials yet">–</span>'));
  // The Overall drawer says the same in a banner. The task drawer and trial view list each trial instead.
  const drawer = (selection: Parameters<typeof Detail>[0]["selection"]) => renderToStaticMarkup(createElement(Detail, { data, selection, onSelect: () => {} }));
  const token = { ...tasks[1], domain: "dapp-development" as const };
  // Overall counts one Concepts task at 50% and two Build tasks at 100%; the Act task is Model only.
  assert.ok(drawer({ agent, mode: "internet" }).includes('<p class="unscored-banner">3 trials have no score yet.</p><p>83% · 3 scored trials</p>'));
  assert.ok(!drawer({ agent, mode: "internet", pillar: "concepts" }).includes("unscored-banner"));
  assert.ok(drawer({ agent, mode: "internet", pillar: "build" }).includes('<p class="unscored-banner">3 trials have no score yet.</p>'));
  const task = drawer({ agent, mode: "internet", evaluation: token });
  assert.ok(!task.includes("unscored-banner"));
  assert.match(task, /Trial 2<\/button><\/td><td><span class="trial-score">.*?<\/span>Not scored<\/span>/);
  assert.ok(!drawer({ agent, mode: "internet", evaluation: token, run: 1 }).includes("unscored-banner"));
  // The Page task never ran: both planned trials get a row that cannot be opened.
  const page2 = drawer({ agent, mode: "internet", evaluation: { ...tasks[2], domain: "dapp-development" } });
  assert.deepEqual([...page2.matchAll(/<tr class="not-run"><td>Trial (\d)<\/td><td>Not run yet<\/td>/g)].map((match) => match[1]), ["1", "2"]);
  assert.ok(!page2.includes('class="run-open"'));
});

test("the task drawer lists a Not run yet row for each planned trial number without a saved trial", () => {
  const data = buildBoard([evaluation], [row({ trial: 2 }), row({ trial: 4, ...error })], false, 5);
  const html = renderToStaticMarkup(createElement(Detail, { data, selection: { evaluation, agent, mode: "internet" }, onSelect: () => {} }));
  const order = [...html.matchAll(/<tr( class="not-run")?><td>(?:<button[^>]*>)?Trial (\d)/g)].map((match) => `${match[2]}${match[1] ? " not run" : ""}`);
  assert.deepEqual(order, ["1 not run", "2", "3 not run", "4", "5 not run"]);
  assert.equal((html.match(/class="run-open"/g) ?? []).length, 2);
  // Without planned attempts nothing is listed as not run.
  const unplanned = renderToStaticMarkup(createElement(Detail, { data: buildBoard([evaluation], [row({ trial: 2 })]),
    selection: { evaluation, agent, mode: "internet" }, onSelect: () => {} }));
  assert.doesNotMatch(unplanned, /Not run yet/);
});

test("unsupported, unrun, and failed cells have distinct states", () => {
  const naBoard = buildBoard([{ ...evaluation, modes: ["vanilla"] }, { ...evaluation, id: "concepts/b" }], [row({ task_id: "concepts/b" })]);
  const na = naBoard.tables.internet.pillars.concepts.evals[0].cells[agentKey(agent)];
  const pendingBoard = buildBoard([evaluation, { ...evaluation, id: "concepts/b" }], [row({ task_id: "concepts/b" })]);
  const pending = pendingBoard.tables.internet.pillars.concepts.evals[0].cells[agentKey(agent)];
  const failed = getCell(evaluation, agent, "internet", [row(failure)]);
  assert.deepEqual([na, pending, failed].map(({ state, score, passed, total }) => ({ state, score, passed, total })), [
    { state: "na", score: null, passed: 0, total: 0 },
    { state: "pending", score: null, passed: 0, total: 0 },
    { state: "score", score: 0, passed: 0, total: 1 },
  ]);
});

test("an error-only cell has no score, and a time limit counts as a failure", () => {
  const pending = getCell(evaluation, agent, "internet", [row(error)]);
  const limited = getCell(evaluation, agent, "internet", [row({ ...failure,
    limit: { type: "time", limit: 300, reason: null }, checks: {
      answer: { passed: false, reason: "Trial reached time limit 300." },
      second: { passed: false, reason: "Trial reached time limit 300." },
    } })]);
  assert.deepEqual([pending.state, pending.score, pending.errors], ["pending", null, 1]);
  assert.deepEqual([limited.state, limited.score, limited.total], ["score", 0, 1]);
  assert.equal(limited.trials[0].issue, "Trial reached time limit 300.");
  assert.equal(limited.trials[0].checks.answer.reason, "Trial reached time limit 300.");
});

test("pillar means give tasks equal weight and skip tasks without scored trials", () => {
  const board = buildBoard([evaluation, { ...evaluation, id: "concepts/b" }, { ...evaluation, id: "concepts/c" },
    { ...evaluation, id: "concepts/d", modes: ["vanilla"] }], [
    row(), row({ task_id: "concepts/b" }), row({ task_id: "concepts/b", trial: 2, ...failure }),
    row({ task_id: "concepts/b", trial: 3, ...failure }), row({ task_id: "concepts/c", ...error }),
  ]);
  const cell = board.tables.internet.pillars.concepts.cells[agentKey(agent)];
  assert.deepEqual({ score: cell.score, passed: cell.passed, total: cell.total, scoredEvals: cell.scoredEvals, errors: cell.errors },
    { score: 2 / 3, passed: 2, total: 4, scoredEvals: 2, errors: 1 });
});

test("mode, agent, model, and effort keep different agents apart", () => {
  const rows = [row(), row({ model: "model-b", ...failure }), row({ agent: "agent-b", ...failure }),
    row({ effort: "low", ...failure }), row({ mode: "vanilla", agent: null, ...failure })];
  const cell = getCell(evaluation, agent, "internet", rows);
  const bare = getCell(evaluation, { ...agent, agent: null }, "vanilla", rows);
  assert.deepEqual([cell.passed, cell.total, bare.passed, bare.total], [1, 1, 0, 1]);
  assert.deepEqual(buildBoard([evaluation], rows).tables.vanilla.agents, [{ model: "model-a", agent: null, effort: "high" }]);
});

test("the knowledge table and its panel data include only declared vanilla tasks", () => {
  const board = buildBoard([evaluation, { ...evaluation, id: "build/token", pillar: "build", modes: ["internet"] }],
    [row({ mode: "vanilla", agent: null })]);
  assert.deepEqual(board.tables.vanilla.pillars.concepts.evals.map((entry) => entry.id), ["concepts/units"]);
  assert.deepEqual(board.tables.vanilla.pillars.build.cells['["model-a",null,"high"]'],
    { state: "empty", score: null, passed: 0, total: 0, errors: 0, missing: 0, cost: null, tokens: null, scoredEvals: 0 });
  assert.equal(board.tables.internet.pillars.build.evals[0].id, "build/token");
});

test("a pillar with no declared tasks for a mode differs from an unsupported task", () => {
  const board = buildBoard([evaluation, { ...evaluation, id: "build/check", pillar: "build", modes: ["vanilla"] }], [row()]);
  assert.deepEqual(board.tables.internet.pillars.act.cells[agentKey(agent)],
    { state: "empty", score: null, passed: 0, total: 0, errors: 0, missing: 0, cost: null, tokens: null, scoredEvals: 0 });
  assert.equal(board.tables.internet.pillars.build.cells[agentKey(agent)].state, "empty");
  assert.equal(board.tables.internet.pillars.build.evals[0].cells[agentKey(agent)].state, "na");
  assert.equal(board.tables.internet.pillars.concepts.cells[agentKey(agent)].score, 1);
});

test("the table and panel both label an empty pillar as No tasks yet", () => {
  const data = buildBoard([evaluation], [row()]);
  const table = renderToStaticMarkup(createElement(Board, { data }));
  const panel = renderToStaticMarkup(createElement(Detail, {
    data, selection: { pillar: "act", agent, mode: "internet" },
    onSelect: () => {},
  }));
  assert.ok(table.includes('aria-label="Act, agent-a / model-a. No tasks yet. Open details."'));
  assert.ok(panel.includes('<p class="muted">No tasks yet</p>'));
  assert.ok(panel.includes("No tasks yet for this mode."));
});

test("the board labels null effort as the provider default", () => {
  const data = buildBoard([evaluation], [row({ effort: null }), row({ effort: "medium" })]);
  const html = renderToStaticMarkup(createElement(Board, { data }));
  assert.ok(html.includes("agent-a · effort provider default</small>"));
  assert.ok(html.includes("agent-a · effort medium</small>"));
});

test("each label shows what the agents spent on the trials under it, errors and refusals included, judges left out", () => {
  // Mint is a security task, so the dapp-development filter hides it from the matrix.
  const build: Eval = { ...evaluation, id: "build/mint", title: "Mint", pillar: "build", area: "Audits", modes: ["internet"] };
  // Agent costs and tokens only. Units: 0.25 + a refused trial 0.5 = 0.75, 100 + 200 tokens.
  // Mint: an error 1 + 2 = 3, 1,000 + 2,000 tokens. Row: 3.75 and 3,300 tokens.
  const rows = [row({ model_cost_usd: 0.25, judge_cost_usd: 0.5, total_tokens: 100 }),
    row({ trial: 2, model_cost_usd: 0.5, judge_cost_usd: null, total_tokens: 200, ...noAnswerTwice("refused") }),
    row({ task_id: "build/mint", status: "error", model_cost_usd: 1, judge_cost_usd: null, total_tokens: 1000 }),
    row({ task_id: "build/mint", trial: 2, status: "failed", model_cost_usd: 2, judge_cost_usd: 0.25, total_tokens: 2000 })];
  const data = buildBoard([evaluation, build], rows);
  const board = (query: string) => renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams(query) }));
  const drawer = (selection: Omit<Selection, "agent" | "mode">, source = data) => spend(renderToStaticMarkup(createElement(Detail, {
    data: source, selection: { agent, mode: "internet", ...selection }, domain: "dapp-development", onSelect: () => {} })));
  // Ignoring refusals and filtering by domain change scores and rows, not what the trials spent.
  for (const query of ["", "refusals=ignore", "domain=dapp-development"]) {
    const html = board(query);
    assert.equal(spend(html), "$3.75 · 3.3K tok", query);
    assert.equal(spend(html.slice(html.indexOf('id="evals"'))), "$3.75 · 3.3K tok", query);
  }
  for (const source of [data, ignoreRefusals(data)]) {
    assert.equal(drawer({}, source), "$3.75 · 3.3K tok");
    assert.equal(drawer({ pillar: "build" }, source), "$3.00 · 3K tok");
    assert.equal(drawer({ pillar: "concepts" }, source), "$0.75 · 300 tok");
    assert.equal(drawer({ evaluation: data.evaluations["concepts/units"] }, source), "$0.75 · 300 tok");
    assert.equal(drawer({ evaluation: data.evaluations["build/mint"], run: 2 }, source), "$2.00 · 2K tok");
  }
  assert.deepEqual(taskSpends(renderToStaticMarkup(createElement(Detail, {
    data, selection: { agent, mode: "internet", pillar: "build" }, onSelect: () => {} }))), ["$3.00 · 3K tok"]);
});

test("unknown usage reads as one dash on the label, the drawer task list and the trials table, and a real zero stays", () => {
  // Units' only trial has no recorded cost, and the runner saved its missing token count as 0.
  // Mint's trial really cost $0 and used no tokens. Swap has no trials yet.
  const mint: Eval = { ...evaluation, id: "concepts/mint", title: "Mint" };
  const swap: Eval = { ...evaluation, id: "concepts/swap", title: "Swap" };
  const data = buildBoard([evaluation, mint, swap], [row({ model_cost_usd: null, total_tokens: 0, ...noAnswerTwice("refused") }),
    row({ task_id: "concepts/mint", status: "error", model_cost_usd: 0, total_tokens: 0 })], false, 1);
  const detail = (selection: Omit<Selection, "agent" | "mode">) => renderToStaticMarkup(createElement(Detail, {
    data, selection: { agent, mode: "internet", ...selection }, onSelect: () => {} }));
  const units = detail({ evaluation: data.evaluations["concepts/units"] });
  assert.equal(spend(units), "–");
  assert.equal(spend(detail({ evaluation: data.evaluations["concepts/units"], run: 1 })), "–");
  assert.equal(spend(detail({ evaluation: data.evaluations["concepts/swap"] })), "–");
  assert.equal(spend(detail({ pillar: "act" })), "–");
  // Trials table: time, tokens, cost.
  assert.match(units, /<td>8\.0s<\/td><td>–<\/td><td>–<\/td>/);
  const zero = detail({ evaluation: data.evaluations["concepts/mint"] });
  assert.equal(spend(zero), "$0 · 0 tok");
  assert.match(zero, /<td>8\.0s<\/td><td>0<\/td><td>\$0<\/td>/);
  const list = detail({ pillar: "concepts" });
  assert.deepEqual(taskSpends(list), ["–", "$0 · 0 tok", "–"]);
  assert.equal(spend(list), "$0 · 0 tok");
  for (const html of [units, detail({ evaluation: data.evaluations["concepts/swap"] })]) assert.ok(!html.includes("0 tok"));
});

test("costs show whole dollars from $10, cents from $1, and two significant digits below", () => {
  assert.deepEqual([164.23, 10, 9.99, 2.934, 1, 0.3, 0.046, 0.023, 0.003, 0].map(money),
    ["$164", "$10", "$9.99", "$2.93", "$1.00", "$0.30", "$0.046", "$0.023", "$0.003", "$0"]);
  assert.equal(money(null), "–");
});

test("the mode switch disables Internet + Skills, enables Model only, and retains skills details", () => {
  const data = buildBoard([{ ...evaluation, modes: ["vanilla", "internet", "skills"] }],
    [row(), row({ mode: "skills", ...failure })]);
  const html = renderToStaticMarkup(createElement(Board, { data }));
  assert.ok(html.includes('aria-label="Which results"'));
  assert.match(html, /aria-checked="true"[^>]*>Internet<\/button>/);
  assert.ok(html.includes(">Measures how agents do Ethereum work with web access, the way developers use them</p>"));
  assert.match(html, /<button[^>]*disabled=""[^>]*>Internet \+ Skills<\/button>/);
  assert.doesNotMatch(html, /<button[^>]*disabled=""[^>]*>Model only<\/button>/);
  const panel = renderToStaticMarkup(createElement(Detail, {
    data, selection: { evaluation, pillar: "concepts", agent, mode: "skills", run: 1 },
    onSelect: () => {},
  }));
  assert.ok(panel.includes('class="trial-heading-score">0%</span>'));
  assert.ok(panel.includes("The answer differs."));
  assert.deepEqual([data.tables.internet.pillars.concepts.cells[agentKey(agent)].score,
    data.tables.skills.pillars.concepts.cells[agentKey(agent)].score], [1, 0]);
});

test("selection decoding accepts known ids and closes unknown or prototype-named ids", () => {
  const data = buildBoard([evaluation], [row()]);
  const input = { agent: agentKey(agent), mode: "internet", eval: evaluation.id, pillar: "concepts", list: true };
  const decode = (value: unknown) => decodeSelection(new URLSearchParams({ d: JSON.stringify(value) }), data);
  assert.deepEqual(decode(input), { agent, mode: "internet", evaluation: data.evaluations["concepts/units"], pillar: "concepts", fromList: true, run: undefined });
  for (const id of ["missing", "constructor", "toString", "__proto__"]) assert.equal(decode({ ...input, eval: id }), null);
  for (const value of [null, [], { ...input, agent: "missing" }, { ...input, mode: "missing" }, { ...input, pillar: "constructor" }]) assert.equal(decode(value), null);
  assert.equal(decodeSelection(new URLSearchParams({ d: "{" }), data), null);
  assert.equal(decodeSelection(new URLSearchParams({ eval: "constructor" }), data), null);
});

test("list rows have one task button and Overall groups them under pillar headings", () => {
  const data = buildBoard([evaluation, { ...evaluation, id: "build/token", pillar: "build" }], [row()]);
  const panel = renderToStaticMarkup(createElement(Detail, { data, selection: { agent, mode: "internet" }, onSelect: () => {} }));
  assert.equal((panel.match(/class="eval-list-row"/g) ?? []).length, 2);
  assert.ok(panel.includes('<h3>Concepts</h3>') && panel.includes('<h3>Build</h3>'));
  assert.ok(panel.includes('class="run-dot" data-state="full"') && panel.includes('class="heat-chip"'));
  const board = renderToStaticMarkup(createElement(Board, { data }));
  assert.equal((board.match(/aria-label="Which results"/g) ?? []).length, 1);
  assert.equal((board.match(/aria-label="Which task results"/g) ?? []).length, 1);
  assert.ok(board.includes('id="eval-concepts-units"') && board.includes('<span class="eval-title">Units</span>'));
  assert.ok(board.includes('<span class="matrix-cell" data-empty="true" title="No trials yet">–</span>'));
  assert.ok(!board.includes("$ / pass"));
  assert.equal((board.match(/class="sort-button"/g) ?? []).length, 4);
});

test("the matrix shares the domain URL, counts matching tasks, and hides empty pillar bands", () => {
  const security: Eval = { ...evaluation, id: "concepts/reentrancy", title: "Reentrancy", area: "Audits", modes: ["internet"] };
  const data = buildBoard([evaluation, security, { ...evaluation, id: "build/token", title: "Token", pillar: "build" }], [row()]);
  for (const [query, titles, count] of [
    ["domain=security", ["Reentrancy"], 1],
    ["domain=dapp-development", ["Units", "Token"], 2],
    ["domain=unknown", ["Units", "Reentrancy", "Token"], 3],
  ] as const) {
    const html = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams(query) }));
    const matrix = html.slice(html.indexOf('id="evals"'));
    assert.deepEqual([...matrix.matchAll(/class="eval-title">([^<]+)/g)].map((match) => match[1]), titles);
    assert.ok(matrix.includes(`<p class="eyebrow">${count} tasks</p>`));
    assert.ok(html.includes('agent-a / model-a. 100%. Open details.'));
    if (query === "domain=security") {
      assert.match(matrix, /aria-pressed="true">Security <span>1<\/span>/);
      assert.equal((matrix.match(/class="pillar-band"/g) ?? []).length, 1);
    }
  }
  const vanilla = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams("evals=vanilla") }));
  assert.match(vanilla, /class="badge border-dashed pointer-events-none"[^>]*disabled=""[^>]*>Security<\/button>/);
  assert.ok(vanilla.includes('<p class="eyebrow">2 tasks</p>'));
});

test("drawer domain scores weight pillars by the domain's task count and respect the selected pillar and mode", () => {
  const tasks: Eval[] = [evaluation, { ...evaluation, id: "concepts/fees", title: "Fees" },
    { ...evaluation, id: "build/token", title: "Token", pillar: "build" },
    { ...evaluation, id: "concepts/reentrancy", title: "Reentrancy", area: "Audits" },
    { ...evaluation, id: "concepts/overflow", title: "Overflow", area: "Audits" }];
  const data = buildBoard(tasks, [row(), row({ task_id: "concepts/fees" }), row({ task_id: "concepts/fees", trial: 2, ...failure }),
    row({ task_id: "build/token", ...failure }), row({ task_id: "concepts/reentrancy", ...failure }),
    row({ task_id: "concepts/overflow" }), row({ task_id: "concepts/overflow", trial: 2, ...failure }),
    row({ task_id: "concepts/overflow", trial: 3, ...error }), row({ mode: "vanilla", agent: null, ...failure })]);
  const panel = renderToStaticMarkup(createElement(Detail, { data, selection: { agent, mode: "internet" }, domain: "security", onSelect: () => {} }));
  // Dapp development: two Concepts tasks at 75% and one Build task at 0% give (2 × 75% + 1 × 0%) ÷ 3.
  assert.match(panel, /aria-pressed="false"><span>Dapp development<\/span><b>50%<\/b><small>4 scored trials<\/small>/);
  assert.match(panel, /aria-pressed="true"><span>Security<\/span><b>25%<\/b><small>3 scored trials<\/small>/);
  // All domains: four Concepts tasks at 50% and one Build task at 0%.
  assert.ok(panel.includes('<p>40% · 7 scored trials</p>'));
  assert.deepEqual([...panel.matchAll(/class="eval-list-title"><b>([^<]+)/g)].map((match) => match[1]), ["Reentrancy", "Overflow"]);
  assert.ok(panel.includes('<h3>Concepts</h3>'));
  assert.ok(!panel.includes('<h3>Build</h3>'));
  const concepts = renderToStaticMarkup(createElement(Detail, { data, selection: { agent, mode: "internet", pillar: "concepts" }, onSelect: () => {} }));
  assert.match(concepts, /<span>Dapp development<\/span><b>75%<\/b><small>3 scored trials<\/small>/);
  const build = renderToStaticMarkup(createElement(Detail, { data, selection: { agent, mode: "internet", pillar: "build" }, onSelect: () => {} }));
  assert.match(build, /disabled=""><span>Security<\/span><small>No tasks yet<\/small>/);
  const vanilla = renderToStaticMarkup(createElement(Detail, { data, selection: { agent: { ...agent, agent: null }, mode: "vanilla" }, onSelect: () => {} }));
  assert.match(vanilla, /<span>Dapp development<\/span><b>0%<\/b><small>1 scored trial<\/small>/);
  assert.match(vanilla, /<span>Security<\/span><small>No trials yet<\/small>/);
});

test("unrun drawer domains and task rows show No trials yet and a dash, including errors without scored trials", () => {
  const data = buildBoard([evaluation,
    { ...evaluation, id: "concepts/reentrancy", title: "Reentrancy", area: "Audits" },
    { ...evaluation, id: "concepts/overflow", title: "Overflow", area: "Audits" },
  ], [row(), row({ task_id: "concepts/overflow", ...error })]);
  const panel = renderToStaticMarkup(createElement(Detail, { data, selection: { agent, mode: "internet" }, domain: "security", onSelect: () => {} }));
  assert.match(panel, /aria-pressed="true"><span>Security<\/span><small>No trials yet<\/small>/);
  assert.ok(panel.includes('<span class="heat-chip" data-empty="true" title="No trials yet"><span>–</span></span>'));
  assert.ok(panel.includes('<span class="heat-chip" data-empty="true" title="1 error. No scored trials."><span>–</span></span>'));
  assert.ok(!panel.includes("0/0"));
  const matrix = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams("domain=security") }));
  assert.ok(matrix.includes('title="No trials yet">–</span>'));
  assert.ok(matrix.includes('title="1 error. No scored trials.\nTrial 1 · Error">–</span>'));
});

test("task details open the instruction and list one button per trial with compact counts", () => {
  const quiz = evaluation;
  const data = buildBoard([quiz], [row(), row({ trial: 2, ...failure, total_tokens: 7000, checks: {
    good: { passed: true, reason: "The units match." }, bad: { passed: false, reason: "The answer differs." },
  } }), row({ trial: 3, ...error })]);
  const selection = { evaluation: quiz, agent, mode: "internet" as const, pillar: "concepts" as const };
  const panel = renderToStaticMarkup(createElement(Detail, { data, selection, onSelect: () => {} }));
  assert.ok(panel.includes('<details class="prompt-disclosure" open=""><summary>Instruction</summary>'));
  assert.ok(panel.includes('<pre>How many wei equal one ether?</pre>'));
  assert.ok(panel.includes('<table class="runs-table">'));
  for (const label of ["Trial", "Trial score", "Checks", "Time", "Tokens", "Cost"]) assert.ok(panel.includes(`<th scope="col">${label}</th>`));
  assert.equal((panel.match(/class="run-open"/g) ?? []).length, 3);
  assert.ok(panel.includes('aria-label="Trial 2 · 0% · 1 of 2 passed. Open trial."'));
  assert.match(panel, /data-state="full"[^>]*><\/span>100%.*data-state="zero"[^>]*><\/span>0%.*data-state="error"[^>]*><svg[^>]*lucide-triangle-alert[^>]*>.*?<\/svg><\/span>Not scored/s);
  assert.ok(panel.includes('<td>1 of 2 passed</td>') && panel.includes('<td>7K</td>') && panel.includes('aria-hidden="true">›</td>'));
  assert.equal((panel.match(/open=""/g) ?? []).length, 1);
  assert.ok(!panel.includes('<ul class="checks">') && !panel.includes('class="run-row"'));
  assert.equal((panel.match(/class="back-button"/g) ?? []).length, 0);
  const fromList = renderToStaticMarkup(createElement(Detail, { data, selection: { ...selection, fromList: true }, onSelect: () => {} }));
  assert.match(fromList, /class="back-button"[\s\S]*?<\/svg>Concepts/);
});

test("trial details show the selected trial, failed reasons first, and a switcher back to all trials", () => {
  const data = buildBoard([evaluation], [row(), row({ trial: 2, ...failure, total_tokens: 7000, trajectory_url: "https://example.com/run.json", checks: {
    good: { passed: true, reason: "Test passed." }, bad: { passed: false, reason: "The answer differs." },
  } }), row({ trial: 3, ...error })]);
  const selection = { evaluation, agent, mode: "internet" as const, fromList: true as const, run: 2 };
  const panel = renderToStaticMarkup(createElement(Detail, { data, selection, onSelect: () => {} }));
  assert.match(panel, /<h1[^>]*>Trial 2 of 3 <span class="trial-heading-score">0%<\/span><\/h1>/);
  assert.ok(panel.includes('<p>Units</p>') && panel.includes("agent-a · effort high</small>"));
  assert.ok(panel.includes('aria-label="Trials"') && panel.includes('aria-pressed="true" aria-label="Trial 2 · 0% · 1 of 2 passed"'));
  assert.match(panel, /Trial 1 <span class="run-dot" data-state="full".*Trial 2 <span class="run-dot" data-state="zero".*Trial 3 <span class="run-dot" data-state="error"/s);
  assert.match(panel, /class="back-button"[\s\S]*?<\/svg>All trials/);
  assert.ok(panel.includes('<code>bad</code>') && panel.includes('<code>good</code>') && panel.includes("The answer differs."));
  assert.ok(panel.indexOf('<code>bad</code>') < panel.indexOf('<code>good</code>'));
  assert.ok(panel.includes("Test passed.") && !panel.includes("Cost source:") && !panel.includes('prompt-disclosure') && !panel.includes('aria-label="Agent modes"'));
  assert.ok(panel.includes('<dl class="run-stats"><div><dt>Time</dt><dd>8.0s</dd></div></dl>') && spend(panel) === "$0.20 · 7K tok");
  assert.ok(panel.includes('<h3>Checks <span>1 of 2</span></h3>'));
  assert.ok(panel.indexOf('class="run-switcher"') < panel.indexOf('class="run-stats"'));
  assert.ok(panel.indexOf('class="run-stats"') < panel.indexOf('class="verifier-verdict"'));
  assert.ok(panel.indexOf('class="verifier-verdict"') < panel.indexOf('class="trajectory-links"'));
  assert.ok(panel.includes('href="https://example.com/run.json" target="_blank" rel="noreferrer">Open trajectory ↗'));
  const passed = renderToStaticMarkup(createElement(Detail, { data, selection: { ...selection, run: 1 }, onSelect: () => {} }));
  assert.match(passed, /<h1[^>]*>Trial 1 of 3 <span class="trial-heading-score">100%<\/span><\/h1>/);
  assert.ok(passed.includes('<code>answer</code>') && passed.includes("The answer matches."));
  const errored = renderToStaticMarkup(createElement(Detail, { data, selection: { ...selection, run: 3 }, onSelect: () => {} }));
  assert.match(errored, /<h1[^>]*>Trial 3 of 3 <span class="trial-heading-score">Not scored<\/span><\/h1>/);
  assert.ok(errored.includes("This trial ended in an error, so it is left out of the score."));
  assert.doesNotMatch(errored, /Sandbox stopped\.|class="verifier-verdict"/);
  const allRuns = renderToStaticMarkup(createElement(Detail, { data, selection: { ...selection, run: undefined }, onSelect: () => {} }));
  assert.ok(allRuns.includes('<table class="runs-table">') && allRuns.includes('prompt-disclosure'));
  assert.match(allRuns, /class="back-button"[\s\S]*?<\/svg>All pillars/);
});

test("trial links keep their task, mode, and list context and reject trials outside that selection", () => {
  const data = buildBoard([{ ...evaluation, modes: ["internet", "skills"] }], [row(), row({ trial: 2, ...failure }), row({ mode: "skills", trial: 3 })]);
  const selection = { evaluation: data.evaluations["concepts/units"], agent, mode: "internet" as const, pillar: "concepts" as const, fromList: true as const, run: 2 };
  const encoded = encodeSelection(selection);
  const input = { agent: '["model-a","agent-a","high"]', mode: "internet", pillar: "concepts", eval: "concepts/units", list: true, run: 2 };
  assert.deepEqual(JSON.parse(encoded), input);
  assert.deepEqual(decodeSelection(new URLSearchParams({ d: encoded }), data), selection);
  assert.deepEqual(JSON.parse(encodeSelection({ ...selection, run: 1 })), { ...input, run: 1 });
  assert.deepEqual(JSON.parse(encodeSelection({ ...selection, run: undefined })),
    { agent: '["model-a","agent-a","high"]', mode: "internet", pillar: "concepts", eval: "concepts/units", list: true });
  const decode = (value: unknown) => decodeSelection(new URLSearchParams({ d: JSON.stringify(value) }), data);
  for (const run of [0, 3, -1, 1.5, "2", null]) assert.equal(decode({ ...input, run }), null);
  assert.equal(decode({ ...input, mode: "skills" }), null);
  assert.equal(decode({ ...input, eval: undefined }), null);
});

test("both results tables fall back to Internet for unavailable URL modes and open Model only", () => {
  const data = buildBoard([{ ...evaluation, modes: ["internet", "skills", "vanilla"] }], [
    row(), row({ mode: "skills", ...failure }), row({ mode: "vanilla", agent: null }),
  ]);
  for (const query of [
    "mode=skills&evals=skills",
    "mode=unknown&evals=unknown",
    "mode=internet&evals=internet",
  ]) {
    const html = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams(query) }));
    const top = html.slice(html.indexOf('id="leaderboard"'), html.indexOf('id="evals"'));
    const bottom = html.slice(html.indexOf('id="evals"'));
    assert.ok(top.includes('class="row-label">Configuration<small>'));
    assert.ok(bottom.includes("<h2>Results by task</h2>"));
    assert.ok(bottom.includes("Task score 100%. Open details."));
    assert.ok(top.includes("agent-a / model-a. 100%. Open details."));
    for (const section of [top, bottom]) assert.match(section, /aria-checked="true"[^>]*>Internet<\/button>/);
  }
  const html = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams("mode=vanilla&evals=vanilla") }));
  const top = html.slice(html.indexOf('id="leaderboard"'), html.indexOf('id="evals"'));
  assert.ok(top.includes('class="row-label">Model<small>'));
  assert.match(top, /aria-checked="true"[^>]*>Model only<\/button>/);
});

test("details link directly to the trial trajectory and show its payment source", () => {
  const data = buildBoard([evaluation], [row({ trajectory_url: "https://example.com/trajectory.json" })]);
  const panel = renderToStaticMarkup(createElement(Detail, { data, selection: { evaluation, agent, mode: "internet", run: 1 }, onSelect: () => {} }));
  assert.ok(panel.includes('href="https://example.com/trajectory.json" target="_blank" rel="noreferrer">Open trajectory ↗'));
  assert.ok(panel.includes("Paid by API key"));
});

test("configurations show one agent logo beside the name, or one provider logo for model-only rows", () => {
  for (const [model, agent, provider, icon, label] of [
    ["anthropic/claude-opus-5-5", "claude-code", "claude", "claude-code"],
    ["anthropic/claude-fable-5-1", "claude-code", "claude", "claude-code", "Fable 5.1"],
    ["openai/gpt-6.1-sol", "codex", "openai", "codex", "GPT-6.1 Sol"],
    ["openai/gpt-6-astra", "codex", "openai", "codex", "GPT-6 Astra"],
    ["openai/gpt-6.2-astra", "codex", "openai", "codex", "GPT-6.2 Astra"],
    ["openai/gpt-6.2-sol", "codex", "openai", "codex", "GPT-6.2 Sol"],
    ["openrouter/moonshotai/kimi-k3.1-pro", "opencode", "openrouter", "opencode", "Kimi K3.1 Pro"],
    ["openrouter/z-ai/glm-5.3", "opencode", "openrouter", "opencode", "GLM 5.3"],
    ["openrouter/deepseek/deepseek-v4.1-flash-1017", "opencode", "openrouter", "opencode", "DeepSeek V4.1 Flash"],
    ["openrouter/x-ai/grok-4.7", "opencode", "openrouter", "opencode", "Grok 4.7"],
    ["openrouter/google/gemini-4-argon", "opencode", "openrouter", "opencode", "Gemini 4 Argon"],
    ["openrouter/google/gemini-4-neon", "opencode", "openrouter", "opencode", "Gemini 4 Neon"],
  ]) {
    const html = renderToStaticMarkup(createElement(Configuration, { agent: { model, agent, effort: null }, cost: null, tokens: 0, plan: false }));
    assert.ok(html.match(/<b>([\s\S]*?)<\/b>/)?.[1].includes(`src="/logos/${icon}.svg"`));
    assert.equal((html.match(/<img /g) ?? []).length, 1);
    const bare = renderToStaticMarkup(createElement(Configuration, { agent: { model, agent: null, effort: null }, cost: null, tokens: 0, plan: false }));
    assert.ok(bare.match(/<b>([\s\S]*?)<\/b>/)?.[1].includes(`src="/logos/${provider}.svg"`));
    assert.equal((bare.match(/<img /g) ?? []).length, 1);
    if (label) {
      assert.ok(html.includes(` ${label}</b>`));
      assert.ok(bare.includes(label));
    }
  }
});

test("row parsing keeps long named-check reasons and reports malformed verdicts with a line number", () => {
  const reason = "The expected answer differs. ".repeat(60).trim();
  assert.equal(parseRows(JSON.stringify(row({ ...failure, checks: { answer: { passed: false, reason } } })), "results.jsonl", [evaluation])[0].checks.answer.reason, reason);
  assert.throws(() => parseRows(`\n${JSON.stringify(row({ status: "invalid" as Row["status"] }))}`, "results.jsonl", [evaluation]), /results.jsonl:2:.*[\s\S]*status/);
});

test("demo loading is explicit and produces scores from fixture rows and catalog", () => {
  const data = loadBoard({ ETHEVALS_DEMO: "1" });
  const cell = data.tables.internet.pillars.concepts.evals.find((entry) => entry.id === "concepts/units")!
    .cells['["Demo model A","Demo agent A","high"]'];
  assert.deepEqual([data.demo, cell.passed, cell.total, cell.score], [true, 2, 3, 2 / 3]);
  assert.throws(() => loadBoard({ ETHEVALS_DEMO: "true" }), /ETHEVALS_DEMO must be 0 or 1/);
  assert.throws(() => loadBoard({ ETHEVALS_DEMO: "1", ETHEVALS_ROWS: "rows.jsonl" }), /Choose ETHEVALS_DEMO or ETHEVALS_ROWS/);
});

test("the board keeps a listed model and drops a retired model with a current task hash", () => {
  const rows = currentRows([row(), row({ model: "retired-model" })], {
    evals: [evaluation], skills_hash: "current-pack", n_attempts: 3, models: ["model-a"],
  });
  assert.deepEqual(rows.map((entry) => entry.model), ["model-a"]);
  const data = buildBoard([evaluation], rows);
  assert.deepEqual(data.tables.internet.agents, [agent]);
  const html = renderToStaticMarkup(createElement(Board, { data }));
  assert.ok(html.includes("agent-a / model-a. 100%. Open details."));
  assert.equal(html.includes("retired-model"), false);
});

test("tile colors and drawer chips compare each score with the best in its column or task row", () => {
  const second = { ...agent, model: "model-b" }, third = { ...agent, model: "model-c" };
  const buildTask: Eval = { ...evaluation, id: "build/vault", title: "Vault", pillar: "build", modes: ["internet"] };
  // Concepts/Units: model-a 100%, model-b 50%, model-c 0%, model-d error only.
  // Build/Vault:    model-a 50%,  model-b 75%, model-c 0%, model-d unrun.
  // Overall:        model-a 75%,  model-b 63%, model-c 0%, model-d error only.
  const data = buildBoard([evaluation, buildTask], [
    row(),
    row({ model: "model-b", trial: 1 }), row({ model: "model-b", trial: 2, ...failure }),
    row({ model: "model-c", ...failure }), row({ model: "model-d", ...error }),
    row({ task_id: buildTask.id, trial: 1 }), row({ task_id: buildTask.id, trial: 2, ...failure }),
    ...[1, 2, 3].map((trial) => row({ task_id: buildTask.id, model: "model-b", trial })),
    row({ task_id: buildTask.id, model: "model-b", trial: 4, ...failure }),
    row({ task_id: buildTask.id, model: "model-c", ...failure }),
  ]);
  const html = renderToStaticMarkup(createElement(Results, { data, query: new URLSearchParams() }));
  const top = html.slice(html.indexOf('id="leaderboard"'), html.indexOf('id="evals"'));
  const bottom = html.slice(html.indexOf('id="evals"'));
  const tileFor = (section: string, label: string) => section.match(new RegExp(`<button class="(?:score|matrix)-cell"[^>]*aria-label="${label}[^>]*>`))?.[0];
  // Overall: gap 12 -> 100 * exp(-12 / 28) = 65.1. Build/Vault: gap 25 -> 100 * exp(-25 / 28) = 40.9.
  assert.match(tileFor(top, "Overall, agent-a / model-a\\.")!, /data-tone="leader"/);
  assert.match(tileFor(top, "Overall, agent-a / model-b\\.")!, /data-tone="trail" style="--heat:65.1%"/);
  assert.match(tileFor(top, "Overall, agent-a / model-c\\.")!, /data-tone="zero"/);
  assert.match(tileFor(top, "Overall, agent-a / model-d\\.")!, /data-empty="true"[^>]*No scored trials\./);
  assert.match(tileFor(top, "Build, agent-a / model-d\\.")!, /data-empty="true"[^>]*No trials yet\./);
  // model-b wins Build & Vault (75%) even while trailing on Overall (63%).
  assert.match(tileFor(top, "Build, agent-a / model-b\\.")!, /data-tone="leader"/);
  assert.match(tileFor(top, "Build, agent-a / model-a\\.")!, /data-tone="trail" style="--heat:40.9%"/);
  assert.match(tileFor(bottom, "Vault, agent-a / model-b\\.")!, /data-tone="leader"/);
  assert.match(tileFor(bottom, "Vault, agent-a / model-a\\.")!, /data-tone="trail" style="--heat:40.9%"/);
  assert.ok(bottom.includes('<span class="matrix-cell" data-empty="true" title="1 error. No scored trials.'));
  const vaultCell = (model: Agent) => data.tables.internet.pillars.build.evals[0].cells[agentKey(model)];
  const vaultPeers = peers(data.tables.internet.agents.map((value) => vaultCell(value).score));
  assert.equal(taskHint(vaultCell(second), vaultPeers).split("\n")[0], "Best on this task");
  assert.equal(taskHint(vaultCell(agent), vaultPeers).split("\n")[0], "\u221225 pts · best 75%");
  const vaultChip = (model: Agent) => renderToStaticMarkup(createElement(Detail, { data, selection: { agent: model, mode: "internet", pillar: "build" }, onSelect: () => {} }))
    .match(/<span class="heat-chip".*?<\/small><\/span>/)?.[0];
  assert.equal(vaultChip(second), '<span class="heat-chip" data-empty="false" data-tone="leader"><span>75%</span><small class="heat-best">best</small></span>');
  assert.equal(vaultChip(agent), '<span class="heat-chip" data-empty="false" data-tone="trail" style="--heat:40.9%"><span>50%</span><small class="heat-best">best 75%</small></span>');
  assert.equal(vaultChip(third), '<span class="heat-chip" data-empty="false" data-tone="zero"><span>0%</span><small class="heat-best">best 75%</small></span>');
});
