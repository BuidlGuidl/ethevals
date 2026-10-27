import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test from "node:test";
import { Tasks } from "../app/evals/tasks";
import { loadTaskCatalog } from "../src/load";

test("the Tasks page renders catalog counts, titles, badges, instructions, and README links without results", (t) => {
  const root = mkdtempSync(path.join(os.tmpdir(), "ethevals-tasks-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(path.join(root, ".catalog"));
  const entries = [
    { id: "act/supply-tokens", pillar: "act", area: "Lending", instruction: "Supply tokens.\nKeep the receipt." },
    { id: "build/zebra-vault", pillar: "build", area: "Lending", instruction: "Build a vault." },
    { id: "concepts/units", pillar: "concepts", area: null, instruction: "Name a unit." },
    { id: "build/alpha-token", pillar: "build", area: "Tokens", instruction: "Build a token." },
    { id: "concepts/fees", pillar: "concepts", instruction: "Explain fees." },
  ].map((entry) => ({ hash: "current", description: "A task.", modes: ["internet"], ...entry }));
  writeFileSync(path.join(root, ".catalog/catalog.json"), JSON.stringify({ skills_hash: "pack", models: [], tasks: entries }));
  const catalog = loadTaskCatalog({ ETHEVALS_ROWS: "missing-results.jsonl" }, root);
  const html = renderToStaticMarkup(createElement(Tasks, { tasks: catalog.evals }));
  for (const [label, count] of [["Total tasks", 5], ["Concepts", 2], ["Build", 2], ["Act", 1]]) {
    assert.ok(html.includes(`<dt class="eyebrow">${label}</dt><dd>${count}</dd>`), `${label} count`);
  }
  for (const [area, count] of [["Lending", 2], ["Tokens", 1]]) {
    assert.ok(html.includes(`<dt>${area}</dt><dd>${count}</dd>`), `${area} count`);
  }
  const rows = [...html.matchAll(/<details class="task-row">(.*?)<\/details>/gs)].map((match) => match[1]);
  assert.deepEqual(rows.map((row) => row.match(/class="task-title">([^<]+)/)?.[1]),
    ["Fees", "Units", "Alpha token", "Zebra vault", "Supply tokens"]);
  assert.deepEqual(rows.map((row) => [...row.matchAll(/class="badge">([^<]+)/g)].map((match) => match[1])),
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
  assert.equal((html.match(/<dd>0<\/dd>/g) ?? []).length, 4);
  assert.ok(html.includes("No tasks yet."));
});

test("the catalog loader selects demo tasks and rejects a blank area", (t) => {
  const root = mkdtempSync(path.join(os.tmpdir(), "ethevals-task-demo-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(path.join(root, "demo"));
  const file = path.join(root, "demo/catalog.json");
  const task = { id: "act/send-token", hash: "demo", pillar: "act", description: "Send a token.",
    instruction: "Send one token.", modes: ["internet"], area: "Tokens" };
  writeFileSync(file, JSON.stringify({ skills_hash: "pack", models: [], tasks: [task] }));
  assert.deepEqual(loadTaskCatalog({ ETHEVALS_DEMO: "1" }, root).evals,
    [{ ...task, title: "Send token" }]);
  writeFileSync(file, JSON.stringify({ skills_hash: "pack", models: [], tasks: [{ ...task, area: " " }] }));
  assert.throws(() => loadTaskCatalog({ ETHEVALS_DEMO: "1" }, root), /cannot load task catalog/);
});
