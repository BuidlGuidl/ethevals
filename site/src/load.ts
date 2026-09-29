import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { buildBoard, pillars, agentKey, type BoardData, type Eval } from "./board";
import { rowSchema, type Row } from "./rows";
import { siteRoot } from "./paths";

// This checks the JSON transport. The runner owns eval declarations and hashes.
const catalogSchema = z.array(z.object({
  id: z.string().min(1), hash: z.string().min(1), pillar: z.enum(pillars),
  type: z.enum(["quiz", "build", "act"]),
  motivation: z.string().min(1), prompt: z.string().min(1),
  choices: z.array(z.string()).nullable().transform((value) => value ?? []),
  modes: z.array(z.enum(["vanilla", "internet", "skills"])).min(1),
})).min(1);

export function loadEvals(filename: string): Eval[] {
  try {
    return catalogSchema.parse(JSON.parse(readFileSync(filename, "utf8"))).map((entry) => {
      const name = entry.id.split("/").at(-1)!.replace(/[-_]/g, " ");
      return { ...entry, title: name.charAt(0).toUpperCase() + name.slice(1) };
    });
  } catch (error) {
    throw new Error(`${filename}: cannot load eval catalog: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export function parseRows(contents: string, filename: string, evaluations: Eval[]): Row[] {
  const current = new Map(evaluations.map((evaluation) => [evaluation.id, evaluation]));
  const identities = new Set<string>();
  return contents.split(/\r?\n/).flatMap((line, index) => {
    if (!line.trim()) return [];
    try {
      const row = rowSchema.parse(JSON.parse(line));
      if (row.mode === "internet" && !row.harness) throw new Error("Internet rows require a harness.");
      if (row.mode === "vanilla" && row.harness !== null) throw new Error("Vanilla rows cannot have a harness.");
      if (row.mode === "vanilla" && row.type !== "quiz") throw new Error("Vanilla rows require a quiz eval.");
      const evaluation = current.get(row.eval_id);
      if (evaluation?.hash === row.eval_hash) {
        if (!evaluation.modes.includes(row.mode)) throw new Error("The eval does not declare this mode.");
        if (evaluation.type !== row.type) throw new Error("The type differs from the current eval.");
      }
      const key = JSON.stringify([row.eval_id, row.eval_hash, agentKey(row), row.mode, row.epoch]);
      if (identities.has(key)) throw new Error(`Duplicate epoch for ${row.eval_id}, ${row.model}, epoch ${row.epoch}.`);
      identities.add(key);
      return [row];
    } catch (error) {
      throw new Error(`${filename}:${index + 1}: ${error instanceof Error ? error.message : String(error)}`);
    }
  });
}

export function loadBoard(env: Record<string, string | undefined> = process.env, root = siteRoot): BoardData {
  if (env.ETHEVALS_DEMO && !["0", "1"].includes(env.ETHEVALS_DEMO)) {
    throw new Error("ETHEVALS_DEMO must be 0 or 1.");
  }
  const demo = env.ETHEVALS_DEMO === "1";
  if (demo && env.ETHEVALS_ROWS) throw new Error("Choose ETHEVALS_DEMO or ETHEVALS_ROWS, not both.");
  if (!demo) {
    const evalsRoot = path.resolve(root, "../evals");
    if (!existsSync(evalsRoot) || !statSync(evalsRoot).isDirectory()) throw new Error(`${evalsRoot}: evals root does not exist.`);
  }
  const evaluations = loadEvals(path.resolve(root, demo ? "demo/catalog.json" : ".catalog/catalog.json"));
  const filename = path.resolve(root, demo ? "demo/rows.jsonl" : env.ETHEVALS_ROWS || "../results/rows.jsonl");
  const exists = existsSync(filename);
  if ((demo || env.ETHEVALS_ROWS) && !exists) throw new Error(`${filename}: results file does not exist.`);
  const rows = exists ? parseRows(readFileSync(filename, "utf8"), filename, evaluations) : [];
  const current = new Map(evaluations.map((evaluation) => [evaluation.id, evaluation.hash]));
  const shown = rows.filter((row) => current.get(row.eval_id) === row.eval_hash);
  console.log(`${filename}${exists ? "" : " (missing; empty board)"}: ${rows.length} read, ${shown.length} current, ${rows.length - shown.length} stale.`);
  return buildBoard(evaluations, shown, demo);
}
