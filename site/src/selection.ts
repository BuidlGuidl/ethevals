import { agentKey, pillars, type Agent, type BoardData, type DisplayEval, type Mode, type Pillar } from "./board";

export type Selection = { agent: Agent; mode: Mode; pillar?: Pillar; evaluation?: DisplayEval; fromList?: true };

export function decodeSelection(query: URLSearchParams, data: BoardData): Selection | null {
  try {
    const value = JSON.parse(query.get("d") ?? "null");
    if (!value || !["internet", "skills", "vanilla"].includes(value.mode)) return null;
    const mode: Mode = value.mode;
    const agent = data.tables[mode].agents.find((item) => agentKey(item) === value.agent);
    if (!agent || (value.pillar !== undefined && !pillars.includes(value.pillar))) return null;
    if (value.eval !== undefined && (typeof value.eval !== "string" || !Object.hasOwn(data.evaluations, value.eval))) return null;
    const evaluation = value.eval === undefined ? undefined : data.evaluations[value.eval];
    if (evaluation && (!evaluation.modes.includes(mode) || (value.pillar && evaluation.pillar !== value.pillar))) return null;
    return { agent, mode, pillar: value.pillar, evaluation, fromList: value.list === true ? true : undefined };
  } catch { return null; }
}
