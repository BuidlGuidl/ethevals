import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, mkdirSync, copyFileSync, rmSync } from "node:fs";
import path from "node:path";
import { siteRoot } from "../src/paths";
import { currentRows, loadCatalog, parseRows } from "../src/load";

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
  if (existsSync(rowsFile)) {
    const rows = parseRows(readFileSync(rowsFile, "utf8"), rowsFile, catalog.evals);
    for (const row of currentRows(rows, catalog)) {
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
