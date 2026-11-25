import Image from "next/image";
import type { ReactNode } from "react";
import { agentDetails, agentLogo, programLabel, modelLabel } from "../src/labels";
import type { Agent } from "../src/board";

// `cost` is an optional extra after the effort, used by the cost prototype.
export function Configuration({ agent, cost }: { agent: Agent; cost?: ReactNode }) {
  const logo = agentLogo(agent);
  return <span title={agentDetails(agent)} className="configuration"><b>
    {logo && <Image className="configuration-icon" src={`/logos/${logo}.svg`} width={14} height={14} alt="" unoptimized />} {modelLabel(agent.model)}</b>
    <small>{agent.agent ? programLabel(agent.agent) : "API call · no tools"} · effort {agent.effort ?? "provider default"}{cost && <> · {cost}</>}</small></span>;
}
