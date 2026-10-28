import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test, { type TestContext } from "node:test";
import { TaskList, Tasks } from "../app/evals/tasks";
import { loadTaskCatalog } from "../src/load";

function taskCatalog(t: TestContext) {
  const root = mkdtempSync(path.join(os.tmpdir(), "ethevals-tasks-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(path.join(root, ".catalog"));
  const entries = [
    { id: "act/supply-tokens", pillar: "act", area: "Lending", instruction: "Supply tokens.\nKeep the receipt." },
    { id: "build/zebra-vault", pillar: "build", area: "Lending", layer: "contracts", instruction: "Build a vault." },
    { id: "concepts/units", pillar: "concepts", area: null, instruction: "Name a unit." },
    { id: "build/alpha-token", pillar: "build", area: "Tokens", layer: "frontend", instruction: "Build a token." },
    { id: "concepts/fees", pillar: "concepts", instruction: "Explain fees." },
  ].map((entry) => ({ hash: "current", description: "A task.", modes: ["internet"], ...entry }));
  writeFileSync(path.join(root, ".catalog/catalog.json"), JSON.stringify({ skills_hash: "pack", n_attempts: 3, models: [], tasks: entries }));
  return loadTaskCatalog({ ETHEVALS_ROWS: "missing-results.jsonl" }, root);
}

function buttons(html: string, label: string) {
  const group = html.split(`aria-label="${label}">`)[1].split("</div>")[0];
  return [...group.matchAll(/<button([^>]*)>(.*?)<\/button>/gs)].map(([, attributes, content]) => ({
    text: content.replace(/<[^>]+>/g, ""),
    pressed: attributes.includes('aria-pressed="true"'),
    disabled: attributes.includes('disabled=""'),
  }));
}

function titles(html: string) {
  return [...html.matchAll(/class="task-title">([^<]+)/g)].map((match) => match[1]);
}

test("the Tasks page renders catalog counts, titles, badges, instructions, and README links without results", (t) => {
  const catalog = taskCatalog(t);
  const html = renderToStaticMarkup(createElement(Tasks, { tasks: catalog.evals }));
  assert.deepEqual(buttons(html, "Filter by pillar"), [
    { text: "Total tasks5", pressed: true, disabled: false },
    { text: "Concepts2", pressed: false, disabled: false },
    { text: "Build2", pressed: false, disabled: false },
    { text: "Act1", pressed: false, disabled: false },
  ]);
  assert.deepEqual(buttons(html, "Filter by area"), [
    { text: "Lending 2", pressed: false, disabled: false },
    { text: "Tokens 1", pressed: false, disabled: false },
  ]);
  assert.ok(html.includes('<p role="status">5 tasks</p>'));
  assert.ok(!html.includes("Clear filters"));
  const rows = [...html.matchAll(/<details class="task-row">(.*?)<\/details>/gs)].map((match) => match[1]);
  assert.deepEqual(rows.map((row) => row.match(/class="task-title">([^<]+)/)?.[1]),
    ["Fees", "Units", "Alpha token", "Zebra vault", "Supply tokens"]);
  assert.deepEqual(rows.map((row) => [...row.matchAll(/class="badge[^"]*">([^<]+)/g)].map((match) => match[1])),
    [["Concepts"], ["Concepts"], ["Build", "Tokens"], ["Build", "Lending"], ["Act", "Lending"]]);
  for (const instruction of ["Explain fees.", "Name a unit.", "Build a token.", "Build a vault.", "Supply tokens. Keep the receipt."]) {
    assert.ok(html.includes(`<pre>${instruction}</pre>`));
  }
  for (const id of ["concepts/fees", "concepts/units", "build/alpha-token", "build/zebra-vault", "act/supply-tokens"]) {
    assert.ok(html.includes(`href="https://github.com/BuidlGuidl/ethevals/blob/main/tasks/${id}/README.md" target="_blank" rel="noreferrer">README on GitHub ↗</a>`));
  }
});

test("the Tasks page renders zero counts and an empty state from an empty catalog", () => {
  const html = renderToStaticMarkup(createElement(Tasks, { tasks: [] }));
  assert.deepEqual(buttons(html, "Filter by pillar").map((button) => button.text), ["Total tasks0", "Concepts0", "Build0", "Act0"]);
  assert.ok(html.includes("No tasks yet."));
});

test("a shared pillar and area URL renders matching tasks and counts for each filter", (t) => {
  const html = renderToStaticMarkup(createElement(TaskList, { tasks: taskCatalog(t).evals,
    query: new URLSearchParams("pillar=build&area=Lending") }));
  assert.deepEqual(titles(html), ["Zebra vault"]);
  assert.deepEqual(buttons(html, "Filter by pillar"), [
    { text: "Total tasks2", pressed: false, disabled: false },
    { text: "Concepts0", pressed: false, disabled: false },
    { text: "Build1", pressed: true, disabled: false },
    { text: "Act1", pressed: false, disabled: false },
  ]);
  assert.deepEqual(buttons(html, "Filter by area"), [
    { text: "Lending 1", pressed: true, disabled: false },
    { text: "Tokens 1", pressed: false, disabled: false },
  ]);
  assert.ok(html.includes('<p role="status">1 task</p>'));
  assert.ok(html.includes(">Clear filters</button>"));
});

test("a pillar URL keeps every area visible and disables an area without matching tasks", (t) => {
  const html = renderToStaticMarkup(createElement(TaskList, { tasks: taskCatalog(t).evals,
    query: new URLSearchParams("pillar=act") }));
  assert.deepEqual(titles(html), ["Supply tokens"]);
  assert.deepEqual(buttons(html, "Filter by area"), [
    { text: "Lending 1", pressed: false, disabled: false },
    { text: "Tokens 0", pressed: false, disabled: true },
  ]);
  assert.deepEqual(buttons(html, "Filter by pillar").map((button) => [button.text, button.pressed]),
    [["Total tasks5", false], ["Concepts2", false], ["Build2", false], ["Act1", true]]);
});

test("an area URL counts its tasks in each pillar", (t) => {
  const html = renderToStaticMarkup(createElement(TaskList, { tasks: taskCatalog(t).evals,
    query: new URLSearchParams("area=Lending") }));
  assert.deepEqual(titles(html), ["Zebra vault", "Supply tokens"]);
  assert.deepEqual(buttons(html, "Filter by pillar").map((button) => button.text),
    ["Total tasks2", "Concepts0", "Build1", "Act1"]);
  assert.deepEqual(buttons(html, "Filter by area").map((button) => [button.text, button.pressed]),
    [["Lending 2", true], ["Tokens 1", false]]);
});

test("unknown URL filters leave the full catalog visible", (t) => {
  const html = renderToStaticMarkup(createElement(TaskList, { tasks: taskCatalog(t).evals,
    query: new URLSearchParams("pillar=other&area=Unknown") }));
  assert.deepEqual(titles(html), ["Fees", "Units", "Alpha token", "Zebra vault", "Supply tokens"]);
  assert.equal(buttons(html, "Filter by pillar")[0].pressed, true);
  assert.ok(!html.includes("Clear filters"));
});

test("valid URL filters with no shared tasks show an empty result and can be cleared", (t) => {
  const html = renderToStaticMarkup(createElement(TaskList, { tasks: taskCatalog(t).evals,
    query: new URLSearchParams("pillar=act&area=Tokens") }));
  assert.deepEqual(titles(html), []);
  assert.ok(html.includes('<p role="status">0 tasks</p>'));
  assert.ok(html.includes("No tasks match these filters."));
  assert.ok(html.includes(">Clear filters</button>"));
});

test("Build shows layer filters that narrow the list and follow the area", (t) => {
  const tasks = taskCatalog(t).evals;
  const html = renderToStaticMarkup(createElement(TaskList, { tasks, query: new URLSearchParams("pillar=build&layer=contracts") }));
  assert.deepEqual(titles(html), ["Zebra vault"]);
  assert.deepEqual(buttons(html, "Filter Build tasks by layer"), [
    { text: "Contracts 1", pressed: true, disabled: false },
    { text: "Frontend 1", pressed: false, disabled: false },
    { text: "Backend 0", pressed: false, disabled: true },
  ]);
  assert.deepEqual(buttons(html, "Filter by area"), [
    { text: "Lending 1", pressed: false, disabled: false },
    { text: "Tokens 0", pressed: false, disabled: true },
  ]);
  const withArea = renderToStaticMarkup(createElement(TaskList, { tasks, query: new URLSearchParams("pillar=build&area=Tokens") }));
  assert.deepEqual(buttons(withArea, "Filter Build tasks by layer").map((button) => button.text), ["Contracts 0", "Frontend 1", "Backend 0"]);
  const withoutBuild = renderToStaticMarkup(createElement(TaskList, { tasks, query: new URLSearchParams("layer=contracts") }));
  assert.ok(!withoutBuild.includes("Filter Build tasks by layer"));
  assert.equal(titles(withoutBuild).length, 5);
});

test("the catalog loader selects demo tasks and rejects a blank area or an unknown layer", (t) => {
  const root = mkdtempSync(path.join(os.tmpdir(), "ethevals-task-demo-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(path.join(root, "demo"));
  const file = path.join(root, "demo/catalog.json");
  const task = { id: "act/send-token", hash: "demo", pillar: "act", description: "Send a token.",
    instruction: "Send one token.", modes: ["internet"], area: "Tokens" };
  writeFileSync(file, JSON.stringify({ skills_hash: "pack", n_attempts: 3, models: [], tasks: [task] }));
  assert.deepEqual(loadTaskCatalog({ ETHEVALS_DEMO: "1" }, root).evals,
    [{ ...task, title: "Send token" }]);
  writeFileSync(file, JSON.stringify({ skills_hash: "pack", n_attempts: 3, models: [], tasks: [{ ...task, area: " " }] }));
  assert.throws(() => loadTaskCatalog({ ETHEVALS_DEMO: "1" }, root), /cannot load task catalog/);
  writeFileSync(file, JSON.stringify({ skills_hash: "pack", n_attempts: 3, models: [], tasks: [{ ...task, layer: "pages" }] }));
  assert.throws(() => loadTaskCatalog({ ETHEVALS_DEMO: "1" }, root), /cannot load task catalog/);
});
