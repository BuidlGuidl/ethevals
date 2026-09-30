export function logLink(url: string | null, bundledFiles: ReadonlySet<string>, viewerBase = "/logs/"): string | null {
  if (!url) return null;
  const filename = decodeURIComponent(new URL(url, "https://board.invalid").pathname.split("/").at(-1)!);
  return bundledFiles.has(filename)
    ? `${viewerBase}?log_file=${encodeURIComponent(`logs/${filename}`)}`
    : url;
}
