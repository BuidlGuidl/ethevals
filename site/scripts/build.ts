import { spawnSync } from "node:child_process";
import path from "node:path";
import { siteRoot } from "../src/paths";

function run(command: string, args: string[], cwd: string) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

if (process.env.ETHEVALS_SAMPLE !== "1") {
  run("uv", ["run", "ethevals", "catalog", "--output", path.join(siteRoot, ".catalog")], path.dirname(siteRoot));
}
run("pnpm", ["exec", "next", "build"], siteRoot);
