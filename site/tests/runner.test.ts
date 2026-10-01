import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { loadEvals, parseRows } from "../src/load";
import { siteRoot } from "../src/paths";

test("the board reads the merged runner's catalog and reference and empty rows", (t) => {
  const scratch = path.join(siteRoot, ".test-tmp");
  mkdirSync(scratch, { recursive: true });
  const root = mkdtempSync(path.join(scratch, "runner-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const site = path.join(root, "site");
  const folder = path.join(root, "evals/concepts/unit");
  mkdirSync(path.join(folder, "scorer"), { recursive: true });
  mkdirSync(path.join(folder, "workspace"));
  writeFileSync(path.join(folder, "eval.yaml"), "motivation: Check units.\nprompt: Name the unit.\nmodes: [vanilla]\n");
  writeFileSync(path.join(folder, "scorer/target.yaml"), 'target: "wei"\n');
  const env = { ...process.env };
  for (const key of ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"]) delete env[key];
  function run(args: string[]) {
    const result = spawnSync("uv", ["run", "ethevals", ...args, "--evals", folder], {
      cwd: path.dirname(siteRoot), env, encoding: "utf8", timeout: 60_000,
    });
    assert.equal(result.status, 0, result.error?.message ?? result.stderr + result.stdout);
    return result.stdout;
  }
  run(["catalog", "--output", path.join(site, ".catalog")]);
  run(["check", "--epochs", "1", "--output", path.join(root, "results")]);
  const evaluations = loadEvals(path.join(site, ".catalog/catalog.json"));
  assert.deepEqual(evaluations.map((evaluation) => evaluation.id),
    ["concepts/unit"]);
  for (const answer of ["reference", "empty"]) {
    const filename = path.join(root, "results", answer, "rows.jsonl");
    const rows = parseRows(readFileSync(filename, "utf8"), filename, evaluations);
    assert.deepEqual(rows.map((row) => [row.eval_id, row.schema_version, row.status]),
      [["concepts/unit", 5, answer === "reference" ? "passed" : "failed"]]);
    assert.equal(rows[0].eval_hash, evaluations.find((evaluation) => evaluation.id === rows[0].eval_id)!.hash);
    assert.equal(rows[0].log_url, null);
  }
});
