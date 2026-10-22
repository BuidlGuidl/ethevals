import Image from "next/image";
import { agentDetails, agentLogo, programLabel, modelLabel } from "../src/labels";
import type { Agent } from "../src/board";

export function Configuration({ agent }: { agent: Agent }) {
  const logo = agentLogo(agent);
  return <span title={agentDetails(agent)} className="configuration"><b>
    {logo && <Image className="configuration-icon" src={`/logos/${logo}.svg`} width={14} height={14} alt="" unoptimized />} {modelLabel(agent.model)}</b>
    <small>{agent.agent ? programLabel(agent.agent) : "API call · no tools"} · effort {agent.effort ?? "provider default"}</small></span>;
}
