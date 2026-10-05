import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const expected = process.argv[2];
assert.ok(expected === "demo" || expected === "empty", "Pass demo or empty.");
const html = readFileSync("out/index.html", "utf8");
assert.ok(existsSync("out/_next/static"), "The export must contain static assets.");
assert.ok(html.includes('id="leaderboard"') && html.includes('id="evals"'), "The export must contain the leaderboard and eval matrix.");
assert.ok(html.includes("Internet + Skills") && html.includes("Model only"));
assert.equal((html.match(/aria-label="Which results"/g) ?? []).length, 1, "The leaderboard must have a mode toggle.");
assert.equal((html.match(/aria-label="Which eval results"/g) ?? []).length, 1, "The matrix must have its own mode toggle.");
assert.ok(existsSync("out/compare/index.html"));
const how = readFileSync("out/how-it-works/index.html", "utf8");
assert.ok(how.includes("Automated, open evals for AI on Ethereum"));
const sections = [...how.matchAll(/<section id="(hw-[^"]+)"/g)].map((match) => match[1]);
assert.deepEqual(sections, ["hw-pipe", "hw-pillars", "hw-modes", "hw-run", "hw-stack", "hw-add"]);
for (const heading of ["One pull request starts everything", "Four pillars", "Three ways to run an eval"]) assert.ok(how.includes(`<h2>${heading}</h2>`));
const modes = how.slice(how.indexOf('<section id="hw-modes"'), how.indexOf('<section id="hw-run"'));
assert.ok(modes.includes('<p class="eyebrow">Modes</p>') && modes.includes('class="modes-grid"'));
assert.equal((modes.match(/<article[ >]/g) ?? []).length, 3);
assert.ok(modes.includes('<article class="model-only">'));
for (const label of ["Model only", "Internet", "Internet + Skills"]) assert.ok(modes.includes(`<p class="eyebrow">${label}</p>`));
assert.ok(modes.includes('href="https://ethskills.com">ethskills</a>') && modes.includes("skill lift on the website."));
assert.ok(!/mode-progression|modes-strip|mode-step|mode-arrow|skill-bracket|Each eval runs in up to three modes\./.test(how));
assert.ok(how.includes('class="diagram pipeline-diagram"') && how.includes('class="diagram run-diagram"'));
const run = how.slice(how.indexOf('<section id="hw-run"'), how.indexOf('<section id="hw-stack"'));
assert.equal((run.match(/class="container-tag"/g) ?? []).length, 3);
for (const label of ["sends transactions", "reads the chain state", "prompt", "workspace/", "Runner", "transcript", "checks", "LLM as judge", "Results + logs", "on the website, one click"]) assert.ok(run.includes(label));
assert.equal((run.match(/class="diagram-file"/g) ?? []).length, 2);
assert.ok(run.includes("Three separate containers. The agent can&#x27;t reach the scorer."));
assert.ok(!/no route|Grader model|Result row|filtered RPC/.test(how));
for (const [, id] of how.matchAll(/href="\/#(eval-[^"]+)"/g)) {
  assert.ok(html.includes(`id="${id}"`), `The example must link to matrix row ${id}.`);
}
if (expected === "demo") {
  assert.ok(html.includes("<strong>Demo data</strong>"), "The demo banner must be visible.");
  assert.ok(html.includes("Demo model A"));
  assert.ok(html.includes("2 of 3 epochs passed"));
  assert.ok(html.includes('aria-label="Concepts, Demo harness A / Demo model A. 83%.'), "The concepts pillar must show the rounded mean of 2/3 and 1/1.");
  assert.ok(html.includes("$ / pass"));
  assert.ok(html.includes('<span class="eval-title">Agent registries</span>'));
} else {
  assert.ok(html.includes("No agent epochs yet") && html.includes("No evals yet"));
  assert.ok(!html.includes("Demo model") && !html.includes("<strong>Demo data</strong>"));
  assert.ok(!html.includes("mockllm/model"));
}
console.log(`PASS: ${expected} static export, leaderboard, matrix, How it works, and Compare.`);
