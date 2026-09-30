import assert from "node:assert/strict";
import test from "node:test";
import { logLink } from "../src/logs";

test("log links open bundled files in the viewer and keep missing files on the release", () => {
  const files = new Set(["epoch one.eval"]);
  assert.equal(logLink("https://github.com/example/evals/releases/download/run/epoch%20one.eval", files),
    "/logs/index.html?log_file=logs%2Fepoch%20one.eval");
  assert.equal(logLink("https://github.com/example/evals/releases/download/run/missing.eval", files),
    "https://github.com/example/evals/releases/download/run/missing.eval");
});
