import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { buildBoard, pillars, agentKey, type BoardData, type Eval } from "./board";
import { rowSchema, type Row } from "./rows";
import { siteRoot } from "./paths";

// This checks the JSON transport. The runner owns task declarations and hashes.
const catalogSchema = z.object({
  skills_hash: z.string().min(1),
  models: z.array(z.string().min(1)),
  tasks: z.array(z.object({
    id: z.string().min(1), hash: z.string().min(1), pillar: z.enum(pillars),
    description: z.string().min(1), instruction: z.string().min(1),
    modes: z.array(z.enum(["vanilla", "internet", "skills"])).min(1),
  })),
});

export function loadCatalog(filename: string): { evals: Eval[]; skills_hash: string; models: string[] } {
  try {
    const catalog = catalogSchema.parse(JSON.parse(readFileSync(filename, "utf8")));
    return {
      skills_hash: catalog.skills_hash,
      models: catalog.models,
      evals: catalog.tasks.map((entry) => {
        const name = entry.id.split("/").at(-1)!.replace(/[-_]/g, " ");
        return { ...entry, title: name.charAt(0).toUpperCase() + name.slice(1) };
      }),
    };
  } catch (error) {
    throw new Error(`${filename}: cannot load task catalog: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export function parseRows(contents: string, filename: string, evaluations: Eval[]): Row[] {
  const current = new Map(evaluations.map((evaluation) => [evaluation.id, evaluation]));
  const identities = new Set<string>();
  return contents.split(/\r?\n/).flatMap((line, index) => {
    if (!line.trim()) return [];
    try {
      const value = JSON.parse(line);
      if (Number.isInteger(value.schema_version) && value.schema_version < 8) return [];
      const row = rowSchema.parse(value);
      if (row.mode !== "vanilla" && !row.agent) throw new Error("Agent rows require an agent.");
      if (row.mode === "vanilla" && row.agent !== null) throw new Error("Vanilla rows cannot have an agent.");
      const evaluation = current.get(row.task_id);
      if (evaluation?.hash === row.task_hash) {
        if (!evaluation.modes.includes(row.mode)) throw new Error("The task does not declare this mode.");
      }
      const key = JSON.stringify([row.task_id, row.task_hash, row.skills_hash, agentKey(row), row.mode, row.trial]);
      if (identities.has(key)) throw new Error(`Duplicate trial for ${row.task_id}, ${row.model}, trial ${row.trial}.`);
      identities.add(key);
      return [row];
    } catch (error) {
      throw new Error(`${filename}:${index + 1}: ${error instanceof Error ? error.message : String(error)}`);
    }
  });
}

export function currentRows(rows: Row[], catalog: ReturnType<typeof loadCatalog>): Row[] {
  const current = new Map(catalog.evals.map((task) => [task.id, task.hash]));
  const models = new Set(catalog.models);
  return rows.filter((row) => current.get(row.task_id) === row.task_hash
    && models.has(row.model)
    && (row.mode !== "skills" || row.skills_hash === catalog.skills_hash));
}

export function loadBoard(env: Record<string, string | undefined> = process.env, root = siteRoot): BoardData {
  if (env.ETHEVALS_DEMO && !["0", "1"].includes(env.ETHEVALS_DEMO)) {
    throw new Error("ETHEVALS_DEMO must be 0 or 1.");
  }
  const demo = env.ETHEVALS_DEMO === "1";
  if (demo && env.ETHEVALS_ROWS) throw new Error("Choose ETHEVALS_DEMO or ETHEVALS_ROWS, not both.");
  const catalog = loadCatalog(path.resolve(root, demo ? "demo/catalog.json" : ".catalog/catalog.json"));
  if (!demo && catalog.evals.length) {
    const tasksRoot = path.resolve(root, "../tasks");
    if (!existsSync(tasksRoot) || !statSync(tasksRoot).isDirectory()) throw new Error(`${tasksRoot}: tasks root does not exist.`);
  }
  const evaluations = catalog.evals;
  const filename = path.resolve(root, demo ? "demo/rows.jsonl" : env.ETHEVALS_ROWS || "../results/rows.jsonl");
  const exists = existsSync(filename);
  if ((demo || env.ETHEVALS_ROWS) && !exists) throw new Error(`${filename}: results file does not exist.`);
  const rows = exists ? parseRows(readFileSync(filename, "utf8"), filename, evaluations) : [];
  const shown = currentRows(rows, catalog);
  console.log(`${filename}${exists ? "" : " (missing; empty board)"}: ${rows.length} read, ${shown.length} current, ${rows.length - shown.length} stale.`);
  return buildBoard(evaluations, shown, demo);
}
