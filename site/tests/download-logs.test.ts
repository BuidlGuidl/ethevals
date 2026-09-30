import assert from "node:assert/strict";
import test from "node:test";
import { parseReleaseLog } from "../scripts/download-logs";

test("release log URLs yield the decoded tag and filename", () => {
  assert.deepEqual(parseReleaseLog("https://github.com/BuidlGuidl/ethevals/releases/download/run%2Fone/epoch%20one.eval"),
    { tag: "run/one", filename: "epoch one.eval" });
  assert.equal(parseReleaseLog("https://example.com/epoch.eval"), null);
  assert.equal(parseReleaseLog("https://github.com/other/repo/releases/download/run/epoch.eval"), null);
  assert.equal(parseReleaseLog("https://github.com/BuidlGuidl/ethevals/releases/download/run/..%2Fepoch.eval"), null);
});
