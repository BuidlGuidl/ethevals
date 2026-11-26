import Image from "next/image";
import { agentLogo, costNote, programLabel, modelLabel } from "../src/labels";
import { Spend } from "./scores";
import type { Agent } from "../src/board";

// `cost` and `tokens` are what the trials under this label spent. `plan` picks the cost's tooltip.
// `seconds` is a single trial's elapsed time, given only in the trial view.
export function Configuration({ agent, cost, tokens, seconds, plan }: {
  agent: Agent; cost: number | null; tokens: number | null; seconds?: number | null; plan: boolean;
}) {
  const logo = agentLogo(agent);
  return <span className="configuration"><b>
    {logo && <Image className="configuration-icon" src={`/logos/${logo}.svg`} width={14} height={14} alt="" unoptimized />} {modelLabel(agent.model)}</b>
    <small>{agent.agent ? programLabel(agent.agent) : "API call · no tools"} · effort {agent.effort ?? "provider default"}</small>
    <small><Spend cost={cost} tokens={tokens} seconds={seconds} note={costNote(plan)} /></small></span>;
}
