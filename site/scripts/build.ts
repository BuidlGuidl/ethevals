import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, mkdirSync, copyFileSync, rmSync } from "node:fs";
import path from "node:path";
import { siteRoot } from "../src/paths";
import { z } from "zod";
import { rowSchema } from "../src/rows";
import { loadCatalog } from "../src/load";

function run(command: string, args: string[], cwd: string) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function build() {
  if (process.env.ETHEVALS_DEMO !== "1") {
    run("uv", ["run", "ethevals", "catalog", "--output", path.join(siteRoot, ".catalog")], path.dirname(siteRoot));
  }
  const destination = path.join(siteRoot, "public/trajectories");
  rmSync(destination, { recursive: true, force: true });
  const rowsFile = path.resolve(siteRoot, process.env.ETHEVALS_DEMO === "1" ? "demo/rows.jsonl" : process.env.ETHEVALS_ROWS || "../results/rows.jsonl");
  const catalog = loadCatalog(path.join(siteRoot, process.env.ETHEVALS_DEMO === "1" ? "demo/catalog.json" : ".catalog/catalog.json"));
  const current = new Map(catalog.evals.map((task) => [task.id, task.hash]));
  const localRow = rowSchema.extend({ trajectory_file: z.string().nullable().optional() });
  if (existsSync(rowsFile)) {
    for (const line of readFileSync(rowsFile, "utf8").split(/\r?\n/).filter((line) => line.trim())) {
      const value = JSON.parse(line);
      if (value.schema_version < 7) continue;
      const row = localRow.parse(value);
      if (current.get(row.task_id) !== row.task_hash || row.mode === "skills" && row.skills_hash !== catalog.skills_hash) continue;
      if (!row.trajectory_url?.startsWith("/trajectories/")) continue;
      if (!/^\/trajectories\/[\w-]+\.json$/.test(row.trajectory_url) || !row.trajectory_file) {
        throw new Error(`${rowsFile}: local trajectory links require a JSON filename and trajectory_file.`);
      }
      mkdirSync(destination, { recursive: true });
      copyFileSync(path.resolve(path.dirname(rowsFile), row.trajectory_file), path.join(destination, path.basename(row.trajectory_url)));
    }
  }
  run("pnpm", ["exec", "next", process.argv[2] ?? "build", ...process.argv.slice(3)], siteRoot);
}

build();
