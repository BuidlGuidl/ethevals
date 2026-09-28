import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { loadBoard } from "../../site/src/load";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/row-visibility.json", import.meta.url), "utf8"));
const scored: string[] = [];
for (const item of fixture.cases) {
  const board = loadBoard({}, path.join(process.argv[2], item.name, "site"));
  const table = board.tables.internet;
  assert.equal(table.subjects.length > 0, item.shown, item.name);
  const cells = table.pillars.concepts.evals.flatMap((entry) => Object.values(entry.cells));
  const final = cells.some((cell) => cell.epochs.some((epoch) => epoch.status !== "error"));
  assert.equal(final, item.publish, item.name);
  if (final) scored.push(item.name);
}
console.log(JSON.stringify(scored));
