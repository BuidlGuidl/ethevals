import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { buildBoard, pillars, subjectKey, type BoardData, type Evaluation } from "./board";
import { rowSchema, type Row } from "./rows";
import { siteRoot } from "./paths";

// This checks the JSON transport. The runner owns eval declarations and hashes.
const catalogSchema = z.array(z.object({
  id: z.string().min(1), hash: z.string().min(1), pillar: z.enum(pillars),
  type: z.enum(["quiz", "scenario", "build", "act"]),
  motivation: z.string().min(1), prompt: z.string().min(1),
  choices: z.array(z.string()).nullable().transform((value) => value ?? []),
  modes: z.array(z.enum(["vanilla", "internet", "skills"])).min(1),
})).min(1);

export function loadEvaluations(filename: string): Evaluation[] {
  try {
    return catalogSchema.parse(JSON.parse(readFileSync(filename, "utf8"))).map((entry) => {
      const name = entry.id.split("/").at(-1)!.replace(/[-_]/g, " ");
      return { ...entry, title: name.charAt(0).toUpperCase() + name.slice(1) };
    });
  } catch (error) {
    throw new Error(`${filename}: cannot load eval catalog: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function isKeyFree(row: Row): boolean {
  return row.answer_kind !== null || row.token_source === "mock";
}

export function parseRows(contents: string, filename: string, evaluations: Evaluation[]): Row[] {
  const current = new Map(evaluations.map((evaluation) => [evaluation.id, evaluation]));
  const identities = new Set<string>();
  return contents.split(/\r?\n/).flatMap((line, index) => {
    if (!line.trim()) return [];
    try {
      const row = rowSchema.parse(JSON.parse(line));
      if (row.mode === "internet" && !row.harness && !isKeyFree(row)) throw new Error("Internet rows require a harness.");
      if (row.mode === "vanilla" && row.harness !== null) throw new Error("Vanilla rows cannot have a harness.");
      if (row.mode === "vanilla" && row.type !== "quiz") throw new Error("Vanilla rows require a quiz eval.");
      const evaluation = current.get(row.eval_id);
      if (evaluation?.hash === row.eval_hash) {
        if (!evaluation.modes.includes(row.mode)) throw new Error("The eval does not declare this mode.");
        if (evaluation.pillar !== row.pillar) throw new Error("The pillar differs from the current eval.");
        if (evaluation.type !== row.type) throw new Error("The type differs from the current eval.");
      }
      const key = JSON.stringify([row.eval_id, row.eval_hash, subjectKey(row), row.mode, row.epoch, row.answer_kind]);
      if (identities.has(key)) throw new Error(`Duplicate epoch for ${row.eval_id}, ${row.model}, epoch ${row.epoch}.`);
      identities.add(key);
      return [row];
    } catch (error) {
      throw new Error(`${filename}:${index + 1}: ${error instanceof Error ? error.message : String(error)}`);
    }
  });
}

export function loadBoard(env: Record<string, string | undefined> = process.env, root = siteRoot): BoardData {
  if (env.ETHEVALS_SAMPLE && !["0", "1"].includes(env.ETHEVALS_SAMPLE)) {
    throw new Error("ETHEVALS_SAMPLE must be 0 or 1.");
  }
  const sample = env.ETHEVALS_SAMPLE === "1";
  if (sample && env.ETHEVALS_ROWS) throw new Error("Choose ETHEVALS_SAMPLE or ETHEVALS_ROWS, not both.");
  if (!sample) {
    const evalsRoot = path.resolve(root, "../evals");
    if (!existsSync(evalsRoot) || !statSync(evalsRoot).isDirectory()) throw new Error(`${evalsRoot}: evals root does not exist.`);
  }
  const evaluations = loadEvaluations(path.resolve(root, sample ? "sample/catalog.json" : ".catalog/catalog.json"));
  const filename = path.resolve(root, sample ? "sample/rows.jsonl" : env.ETHEVALS_ROWS || "../results/rows.jsonl");
  const exists = existsSync(filename);
  if ((sample || env.ETHEVALS_ROWS) && !exists) throw new Error(`${filename}: results file does not exist.`);
  const rows = exists ? parseRows(readFileSync(filename, "utf8"), filename, evaluations) : [];
  const current = new Map(evaluations.map((evaluation) => [evaluation.id, evaluation.hash]));
  const counts = { shown: 0, stale: 0, keyFree: 0, skills: 0 };
  const shown = rows.filter((row) => {
    if (isKeyFree(row)) { counts.keyFree++; return false; }
    if (current.get(row.eval_id) !== row.eval_hash) { counts.stale++; return false; }
    if (row.mode === "skills") { counts.skills++; return false; }
    counts.shown++;
    return true;
  });
  const logBase = sample ? "/sample" : env.ETHEVALS_LOG_BASE || "";
  if (logBase && !/^https?:\/\/[^/]+(?:\/.*)?$/.test(logBase) && !/^\/(?!\/)/.test(logBase)) {
    throw new Error("ETHEVALS_LOG_BASE must be an HTTP URL or a path starting with one slash.");
  }
  console.log(`${filename}${exists ? "" : " (missing; empty board)"}: ${rows.length} read, ${counts.shown} shown, ${counts.stale} stale, ${counts.keyFree} key-free, ${counts.skills} skills.`);
  return buildBoard(evaluations, shown, sample, logBase);
}
