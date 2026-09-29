import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { loadBoard, loadEvaluations, parseRows } from "../src/load";
import { siteRoot } from "../src/paths";

test("the board reads the merged runner's catalog and reference and empty rows", (t) => {
  const scratch = path.join(siteRoot, ".test-tmp");
  mkdirSync(scratch, { recursive: true });
  const root = mkdtempSync(path.join(scratch, "runner-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const site = path.join(root, "site");
  mkdirSync(path.join(root, "evals"));
  const env = { ...process.env };
  for (const key of ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"]) delete env[key];
  function run(args: string[]) {
    const result = spawnSync("uv", ["run", "ethevals", ...args], {
      cwd: path.dirname(siteRoot), env, encoding: "utf8", timeout: 60_000,
    });
    assert.equal(result.status, 0, result.error?.message ?? result.stderr + result.stdout);
    return result.stdout;
  }
  run(["catalog", "--output", path.join(site, ".catalog")]);
  run(["check", "--evals", "evals/concepts/agent-registries", "--epochs", "1", "--output", path.join(root, "results")]);
  const evaluations = loadEvaluations(path.join(site, ".catalog/catalog.json"));
  assert.deepEqual(evaluations.map((evaluation) => evaluation.id),
    ["building/erc20-points-token", "concepts/agent-registries", "concepts/wei-per-ether", "transactions/send-six-decimal-token"]);
  for (const answer of ["reference", "empty"]) {
    const filename = path.join(root, "results", answer, "rows.jsonl");
    const rows = parseRows(readFileSync(filename, "utf8"), filename, evaluations);
    assert.deepEqual(rows.map((row) => [row.eval_id, row.schema_version, row.status]),
      [["concepts/agent-registries", 4, answer === "reference" ? "passed" : "failed"]]);
    assert.equal(rows[0].eval_hash, evaluations.find((evaluation) => evaluation.id === rows[0].eval_id)!.hash);
    assert.equal(rows[0].log_url, null);

  }
  const board = loadBoard({}, site);
  assert.deepEqual([board.tables.internet.subjects, board.tables.vanilla.subjects], [[], []]);
});
