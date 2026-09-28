import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { parse } from "yaml";
import { z } from "zod";
import { boardRows, pillars, subjectKey, type BoardData, type Evaluation, type Row } from "./board";

const mode = z.enum(["vanilla", "internet", "skills"]);
const evalType = z.enum(["quiz", "scenario", "build", "act"]);
const declaration = z.object({
  title: z.string().min(1).optional(),
  type: evalType,
  motivation: z.string().min(1),
  prompt: z.string().min(1),
  choices: z.array(z.string()).default([]),
  modes: z.array(mode).min(1),
});
const count = z.number().int().nonnegative();
const measure = z.number().nonnegative().nullable();
const rowSchema = z.object({
  schema_version: z.literal(2),
  eval_id: z.string().min(1),
  eval_hash: z.string().min(1),
  pillar: z.enum(pillars),
  type: evalType,
  mode,
  harness: z.string().min(1).nullable(),
  model: z.string().min(1),
  effort: z.string().nullable(),
  answer_kind: z.string().nullable(),
  epoch: z.number().int().positive(),
  status: z.enum(["passed", "failed", "error"]),
  passed: z.boolean().nullable(),
  checks: z.record(z.string(), z.object({ passed: z.boolean(), reason: z.string().min(1) })),
  error_kind: z.string().nullable(),
  error_reason: z.string().nullable(),
  total_tokens: count,
  token_source: z.string(),
  model_cost_usd: measure,
  grader_cost_usd: measure,
  model_cost_source: z.string(),
  grader_cost_source: z.string(),
  total_seconds: measure,
  working_seconds: measure,
  log_file: z.string().min(1),
}).superRefine((row, context) => {
  const checks = Object.values(row.checks);
  const consistent = row.status === "error" ? row.passed === null
    : checks.length > 0 && row.passed === (row.status === "passed")
      && row.passed === checks.every((check) => check.passed);
  if (!consistent) context.addIssue({ code: "custom", message: "Status, verdict, and checks disagree." });
});

// Match inspect-runner/ethevals/loader.py, including byte lengths and traversal order.
const ignoredNames = new Set([".DS_Store", "out", "cache", "lib", "__pycache__", ".pytest_cache"]);
export function evalHash(folder: string): string {
  const digest = createHash("sha256");
  function add(bytes: Buffer) {
    const length = Buffer.alloc(8);
    length.writeBigUInt64BE(BigInt(bytes.length));
    digest.update(length).update(bytes);
  }
  function walk(directory: string) {
    for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => Buffer.compare(Buffer.from(a.name), Buffer.from(b.name)))) {
      if (ignoredNames.has(entry.name)) continue;
      const file = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) throw new Error(`${file}: symlinks are not allowed in an eval folder.`);
      if (entry.isDirectory()) walk(file);
      else if (entry.isFile()) {
        add(Buffer.from(path.relative(folder, file).split(path.sep).join("/")));
        add(readFileSync(file));
      }
    }
  }
  walk(folder);
  return digest.digest("hex");
}

export function loadEvaluations(root: string): Evaluation[] {
  const evaluations: Evaluation[] = [];
  for (const pillar of pillars) {
    const directory = path.join(root, pillar);
    if (!existsSync(directory)) continue;
    for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name, "en"))) {
      if (!entry.isDirectory()) continue;
      const folder = path.join(directory, entry.name);
      const filename = path.join(folder, "eval.yaml");
      if (!existsSync(filename)) continue;
      const result = declaration.safeParse(parse(readFileSync(filename, "utf8")));
      if (!result.success) throw new Error(`${filename}: ${result.error.message}`);
      const title = entry.name.replace(/[-_]/g, " ");
      evaluations.push({ ...result.data, id: `${pillar}/${entry.name}`, hash: evalHash(folder), pillar,
        title: result.data.title ?? title.charAt(0).toUpperCase() + title.slice(1) });
    }
  }
  return evaluations;
}

export function parseRows(contents: string, filename: string): Row[] {
  return contents.split(/\r?\n/).flatMap((line, index) => {
    if (!line.trim()) return [];
    try {
      return [rowSchema.parse(JSON.parse(line))];
    } catch (error) {
      throw new Error(`${filename}:${index + 1}: ${error instanceof Error ? error.message : String(error)}`);
    }
  });
}

export function loadBoard(env: Record<string, string | undefined> = process.env, siteRoot = process.cwd()): BoardData {
  if (env.ETHEVALS_SAMPLE && !["0", "1"].includes(env.ETHEVALS_SAMPLE)) {
    throw new Error("ETHEVALS_SAMPLE must be 0 or 1.");
  }
  const sample = env.ETHEVALS_SAMPLE === "1";
  if (sample && env.ETHEVALS_ROWS) throw new Error("Choose ETHEVALS_SAMPLE or ETHEVALS_ROWS, not both.");
  const evaluations = loadEvaluations(path.resolve(siteRoot, sample ? "sample/evals" : "../evals"));
  const filename = path.resolve(siteRoot, sample ? "sample/rows.jsonl" : env.ETHEVALS_ROWS || "../results/paid/rows.jsonl");
  if ((sample || env.ETHEVALS_ROWS) && !existsSync(filename)) throw new Error(`${filename}: results file does not exist.`);
  const rows = boardRows(evaluations, existsSync(filename) ? parseRows(readFileSync(filename, "utf8"), filename) : []);
  const identities = new Set<string>();
  for (const row of rows) {
    const key = JSON.stringify([row.eval_id, row.eval_hash, subjectKey(row), row.mode, row.epoch]);
    if (identities.has(key)) throw new Error(`${filename}: duplicate epoch for ${row.eval_id}, ${row.model}, epoch ${row.epoch}.`);
    identities.add(key);
  }
  const logBase = sample ? "/sample" : env.ETHEVALS_LOG_BASE || "";
  if (logBase && !/^https?:\/\/[^/]+(?:\/.*)?$/.test(logBase) && !/^\/(?!\/)/.test(logBase)) {
    throw new Error("ETHEVALS_LOG_BASE must be an HTTP URL or a path starting with one slash.");
  }
  return { sample, evaluations, rows, logBase };
}
