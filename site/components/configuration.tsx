import { agentDetails, harnessLabel, modelLabel } from "../src/labels";
import type { Agent } from "../src/board";

export function Configuration({ agent }: { agent: Agent }) {
  return <span title={agentDetails(agent)} className="configuration"><b>{modelLabel(agent.model)}</b>
    <small>{agent.harness ? harnessLabel(agent.harness) : "API call · no tools"} · effort {agent.effort ?? "provider default"}</small></span>;
}
