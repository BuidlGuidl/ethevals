// Prints Overall and pillar scores for every Internet agent under each scoring version, as a markdown table.
// Run from site/ after a build has written .catalog: pnpm exec tsx scripts/scoring-table.ts
import { agentKey, pillars, scoreBoard, type Pillar } from "../src/board";
import { agentLabel, names, scoringCopy } from "../src/labels";
import { loadBoard } from "../src/load";
import { scorings } from "../src/scoring";

const data = loadBoard();
const boards = scorings.map((scoring) => scoreBoard(data, scoring).tables.internet.summaries);
const score = (value: number | null) => value === null ? "–" : (value * 100).toFixed(1);
const agents = [...data.tables.internet.agents].sort((a, b) =>
  (boards[0][agentKey(b)].scores.overall ?? -1) - (boards[0][agentKey(a)].scores.overall ?? -1));
for (const key of ["overall", ...pillars] as ("overall" | Pillar)[]) {
  console.log(`\n### ${key === "overall" ? "Overall" : names[key]}\n`);
  console.log(`| Agent | ${scorings.map((scoring) => scoringCopy.names[scoring]).join(" | ")} |`);
  console.log(`| --- | ${scorings.map(() => "---:").join(" | ")} |`);
  for (const agent of agents) {
    console.log(`| ${agentLabel(agent)} | ${boards.map((summaries) => score(summaries[agentKey(agent)].scores[key])).join(" | ")} |`);
  }
}
