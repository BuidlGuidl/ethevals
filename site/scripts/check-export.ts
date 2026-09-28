import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const expected = process.argv[2];
assert.ok(expected === "sample" || expected === "empty", "Pass sample or empty.");
const html = readFileSync("out/index.html", "utf8");
assert.ok(existsSync("out/_next/static"), "The export must contain static assets.");
assert.ok(html.includes("Agent table") && html.includes("Knowledge table"));
if (expected === "sample") {
  assert.ok(html.includes("<strong>Sample data</strong>"), "The sample banner must be visible.");
  assert.ok(html.includes("Sample model A"));
  assert.ok(html.includes("2 of 3 epochs passed"));
  assert.ok(html.includes("83%"), "The concepts pillar must show the rounded mean of 2/3 and 1/1.");
} else {
  assert.ok(html.includes("No agent epochs yet") && html.includes("No knowledge epochs yet"));
  assert.ok(!html.includes("Sample model") && !html.includes("<strong>Sample data</strong>"));
  assert.ok(!html.includes("mockllm/model"));
}
console.log(`PASS: ${expected} static export, tables, and data labels.`);
