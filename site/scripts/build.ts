import { spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { siteRoot } from "../src/paths";

function run(command: string, args: string[], cwd: string) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

if (process.env.ETHEVALS_DEMO !== "1") {
  run("uv", ["run", "ethevals", "catalog", "--output", path.join(siteRoot, ".catalog")], path.dirname(siteRoot));
}
const logs = path.join(siteRoot, ".logs");
if (existsSync(logs) && readdirSync(logs, { withFileTypes: true }).some((file) => file.isFile() && file.name.endsWith(".eval"))) {
  run("uv", ["run", "inspect", "view", "bundle", "--log-dir", logs,
    "--output-dir", path.join(siteRoot, "public/logs"), "--overwrite"], path.dirname(siteRoot));
}
run("pnpm", ["exec", "next", process.argv[2] ?? "build", ...process.argv.slice(3)], siteRoot);
