import Image from "next/image";
import { agentLogo, costNote, programLabel, modelLabel } from "../src/labels";
import { Hint, money } from "./scores";
import type { Agent } from "../src/board";

// `cost` is what the trials under this label cost. `plan` picks its tooltip.
export function Configuration({ agent, cost, plan }: { agent: Agent; cost: number | null; plan: boolean }) {
  const logo = agentLogo(agent), note = cost === null ? undefined : costNote(plan);
  const amount = <span className={note ? "configuration-cost has-hint" : "configuration-cost"} tabIndex={note ? 0 : undefined}>{money(cost)}</span>;
  return <span className="configuration"><b>
    {logo && <Image className="configuration-icon" src={`/logos/${logo}.svg`} width={14} height={14} alt="" unoptimized />} {modelLabel(agent.model)}</b>
    <small>{agent.agent ? programLabel(agent.agent) : "API call · no tools"} · effort {agent.effort ?? "provider default"} · {note ? <Hint text={note}>{amount}</Hint> : amount}</small></span>;
}
