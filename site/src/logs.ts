export function logLink(url: string | null, bundledFiles: ReadonlySet<string>): string | null {
  if (!url) return null;
  const filename = decodeURIComponent(new URL(url, "https://board.invalid").pathname.split("/").at(-1)!);
  return bundledFiles.has(filename)
    ? `/logs/index.html?log_file=${encodeURIComponent(`logs/${filename}`)}`
    : url;
}
