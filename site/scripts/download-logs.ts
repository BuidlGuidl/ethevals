import { existsSync } from "node:fs";
import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";

export function parseReleaseLog(url: string): { tag: string; filename: string } | null {
  try {
    const parsed = new URL(url);
    if (parsed.origin !== "https://github.com") return null;
    const match = /^\/BuidlGuidl\/ethevals\/releases\/download\/([^/]+)\/([^/]+)$/.exec(parsed.pathname);
    if (!match) return null;
    const tag = decodeURIComponent(match[1]);
    const filename = decodeURIComponent(match[2]);
    if (!filename.endsWith(".eval") || /[/\\\0]/.test(filename)) return null;
    return { tag, filename };
  } catch {
    return null;
  }
}

export async function downloadLogs(rowsFile: string, directory: string): Promise<void> {
  const token = process.env.ETHEVALS_LOGS_TOKEN;
  if (!token) return;
  let warned = false;
  function warn() {
    if (!warned) console.warn("Warning: Could not download some run logs. Unbundled logs keep their GitHub release links.");
    warned = true;
  }
  async function request(url: string, accept: string) {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, Accept: accept },
      signal: AbortSignal.timeout(60_000),
    });
    if (!response.ok) throw new Error("Log request failed.");
    return response;
  }
  try {
    if (!existsSync(rowsFile)) return;
    const releases = new Map<string, Set<string>>();
    for (const line of (await readFile(rowsFile, "utf8")).split(/\r?\n/)) {
      if (!line.trim()) continue;
      const log = parseReleaseLog(JSON.parse(line).log_url);
      if (!log || existsSync(path.join(directory, log.filename))) continue;
      if (!releases.has(log.tag)) releases.set(log.tag, new Set());
      releases.get(log.tag)!.add(log.filename);
    }
    for (const [tag, filenames] of releases) {
      try {
        const response = await request(`https://api.github.com/repos/BuidlGuidl/ethevals/releases/tags/${encodeURIComponent(tag)}`, "application/vnd.github+json");
        const release = await response.json() as { assets: { name: string; url: string }[] };
        for (const filename of filenames) {
          const temporary = path.join(directory, `${filename}.part`);
          try {
            const asset = release.assets.find((asset) => asset.name === filename);
            if (!asset || !/^https:\/\/api\.github\.com\/repos\/BuidlGuidl\/ethevals\/releases\/assets\/\d+$/.test(asset.url)) {
              throw new Error("Log asset is missing.");
            }
            const download = await request(asset.url, "application/octet-stream");
            const contents = Buffer.from(await download.arrayBuffer());
            await mkdir(directory, { recursive: true });
            await writeFile(temporary, contents);
            await rename(temporary, path.join(directory, filename));
          } catch {
            warn();
          } finally {
            await rm(temporary, { force: true });
          }
        }
      } catch {
        warn();
      }
    }
  } catch {
    warn();
  }
}
