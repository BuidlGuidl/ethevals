"use client";
import { useSyncExternalStore } from "react";
function subscribe(callback: () => void) {
  window.addEventListener("popstate", callback);
  window.addEventListener("board-url", callback);
  return () => { window.removeEventListener("popstate", callback); window.removeEventListener("board-url", callback); };
}
// Static export avoids useSearchParams, which needs a Suspense boundary.
// The server snapshot is empty on purpose; the client reads the URL after hydration.
export function useQuery() {
  return new URLSearchParams(useSyncExternalStore(subscribe, () => window.location.search, () => ""));
}
export function updateQuery(values: Record<string, string | null>, push = false) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(values)) {
    if (value === null) url.searchParams.delete(key); else url.searchParams.set(key, value);
  }
  window.history[push ? "pushState" : "replaceState"](null, "", url);
  window.dispatchEvent(new Event("board-url"));
}
