import { agentKey, pillars } from "../src/board";
import { agentLabel, names } from "../src/labels";
import { loadBoard } from "../src/load";

const { agents, summaries } = loadBoard().tables.internet;
const ranked = [...agents].sort((a, b) =>
  (summaries[agentKey(b)].scores.overall ?? -1) - (summaries[agentKey(a)].scores.overall ?? -1));
const score = (value: number | null) => value === null ? "–" : (value * 100).toFixed(1);

console.log(`| Configuration | Overall | ${pillars.map((pillar) => names[pillar]).join(" | ")} |`);
console.log("| --- | ---: | ---: | ---: | ---: |");
for (const agent of ranked) {
  const { scores } = summaries[agentKey(agent)];
  console.log(`| ${agentLabel(agent)} | ${[scores.overall, ...pillars.map((pillar) => scores[pillar])].map(score).join(" | ")} |`);
}
