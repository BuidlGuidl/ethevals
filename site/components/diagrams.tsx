import { FileText, Cpu, ShieldCheck, GitMerge, Terminal, GitPullRequest, Table2, Database, Bot, Box, Scale, Check, Play, type LucideIcon } from "lucide-react";

type Node = { id: string; x: number; y: number; width?: number; height?: number; title: string; lines: string[]; icon: LucideIcon; kind?: "auto" | "dest"; container?: boolean; files?: string[]; note?: string };
function DiagramNode({ node }: { node: Node }) {
  const Icon = node.icon;
  return <g className={`diagram-node ${node.kind ?? "phase"}${node.container ? " container" : ""}`}>
    <rect className="diagram-box" x={node.x} y={node.y} width={node.width ?? 180} height={node.height ?? 108} rx="10" />
    <Icon className="diagram-icon" x={node.x + 16} y={node.y + 15} width={24} height={24} strokeWidth={1.6} />
    {node.container && <g className="container-tag"><rect x={node.x + (node.width ?? 180) - 92} y={node.y + 15} width="74" height="22" rx="4" />
      <text x={node.x + (node.width ?? 180) - 55} y={node.y + 30} textAnchor="middle">container</text></g>}
    <text className="diagram-title" x={node.x + 18} y={node.y + 62}>{node.title}</text>
    {node.lines.map((line, i) => <text key={i} className="diagram-sub" x={node.x + 18} y={node.y + 84 + i * 17}>{line}</text>)}
    {node.files?.map((file, i) => <g key={file}><FileText className="diagram-icon" x={node.x + 18} y={node.y + 107 + i * 23} width="14" height="14" strokeWidth={1.6} />
      <text className="diagram-file" x={node.x + 40} y={node.y + 119 + i * 23}>{file}</text></g>)}
    {node.note && <text className="diagram-sub diagram-dim" x={node.x + 18} y={node.y + 171}>{node.note}</text>}
  </g>;
}
function Arrows({ id }: { id: string }) {
  return <defs>{["phase", "auto"].map((kind) => <marker key={kind} id={`${id}-${kind}`} className={`diagram-marker ${kind}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M1.5 1.5 8.5 5 1.5 8.5" /></marker>)}</defs>;
}
function Edge({ d, kind = "auto", id, index = 0 }: { d: string; kind?: string; id: string; index?: number }) {
  return <g className={`diagram-edge ${kind}`}><path d={d} markerEnd={`url(#${id}-${kind})`} />
    <path className="diagram-pulse" d={d} pathLength="100" style={{ animationDelay: `${index * .45}s` }} /></g>;
}
function elbow(x1: number, y1: number, middle: number, y2: number, x2: number) {
  const r = 8, dir = y2 > y1 ? 1 : -1;
  return `M${x1} ${y1}H${middle-r}Q${middle} ${y1} ${middle} ${y1+dir*r}V${y2-dir*r}Q${middle} ${y2} ${middle+r} ${y2}H${x2}`;
}

export function PipelineDiagram() {
  const nodes: Node[] = [
    { id: "eval", x: 20, y: 84, title: "Add or edit an eval", lines: ["a folder: prompt, files, scoring"], icon: FileText },
    { id: "model", x: 20, y: 246, title: "Add a model", lines: ["one entry in config.yaml"], icon: Cpu },
    { id: "checks", x: 240, y: 165, title: "PR: validity checks", lines: ["checked with a mock model"], icon: ShieldCheck },
    { id: "merge", x: 460, y: 165, title: "Merge to main", lines: ["a maintainer reviews"], icon: GitMerge },
    { id: "ci", x: 680, y: 66, title: "CI runs only what's new", lines: ["every agent and model"], icon: Terminal, kind: "auto" },
    { id: "pr", x: 900, y: 66, title: "Results PR", lines: ["results + logs"], icon: GitPullRequest, kind: "auto" },
    { id: "website", x: 1120, y: 66, title: "Merge → website", lines: ["the board updates"], icon: Table2, kind: "dest" },
    { id: "hf", x: 680, y: 264, title: "Publish HF dataset", lines: ["model-only evals"], icon: Database, kind: "auto" },
  ];
  const edges = [
    ["phase", elbow(200, 138, 220, 219, 237)], ["phase", elbow(200, 300, 220, 219, 237)], ["phase", "M420 219H457"],
    ["auto", elbow(640, 219, 660, 120, 677)], ["auto", elbow(640, 219, 660, 318, 677)],
    ["auto", "M860 120H897"], ["auto", "M1080 120H1117"],
  ];
  return <svg className="diagram pipeline-diagram" viewBox="0 0 1320 400" role="img" aria-labelledby="pipeline-title pipeline-desc">
    <title id="pipeline-title">From pull request to website</title><desc id="pipeline-desc">Eval and model pull requests pass validity checks with a mock model and maintainer review. After merge, CI runs new epochs for every agent and model. A results pull request updates the website. Model-only evals also go to Hugging Face.</desc>
    <Arrows id="pipeline-arrow" />
    {[["1 · Contribute", 20, 200], ["2 · Review", 240, 640], ["3 · Automatic on main", 680, 1300]].map(([label, start, end], index) => <g key={label} className={`diagram-zone ${index === 2 ? "auto" : "phase"}`}><path d={`M${start} 34H${end}`} /><text x={start} y="22">{label}</text></g>)}
    {edges.map(([kind, d], index) => <Edge key={index} d={d} kind={kind} id="pipeline-arrow" index={index} />)}
    {nodes.map((node) => <DiagramNode key={node.id} node={node} />)}
  </svg>;
}

export function RunDiagram() {
  const nodes: Node[] = [
    { id: "agent", x: 20, y: 30, width: 320, height: 188, title: "Agent", lines: ["Claude Code, Codex or OpenCode"], files: ["prompt", "workspace/"], note: "+ Ethereum skills, in skills mode", icon: Bot, container: true },
    { id: "chain", x: 500, y: 30, width: 320, height: 188, title: "Chain", lines: ["Anvil: a fresh chain or a mainnet fork"], icon: Box, container: true },
    { id: "scorer", x: 980, y: 30, width: 320, height: 188, title: "Scorer", lines: ["reads the chain and checks the result"], icon: ShieldCheck, container: true },
    { id: "runner", x: 20, y: 310, width: 320, height: 135, title: "Runner", lines: ["collects the agent's transcript"], icon: Play },
    { id: "judge", x: 500, y: 310, width: 320, height: 135, title: "LLM as judge", lines: ["reads the transcript,", "answers yes-or-no questions"], icon: Scale },
    { id: "result", x: 980, y: 310, width: 320, height: 135, title: "Results + logs", lines: ["on the website, one click", "from the full log"], icon: Check, kind: "dest" },
  ];
  return <svg className="diagram run-diagram" viewBox="0 0 1320 470" role="img" aria-labelledby="run-title run-desc">
    <title id="run-title">Inside one run</title><desc id="run-desc">Agent, chain and scorer run in three separate containers. The agent gets only its prompt and workspace and sends transactions to the chain. The scorer reads the chain state after the agent stops. The agent can&apos;t reach the scorer. The runner collects the transcript for an LLM to judge. The scorer&apos;s checks and the judge&apos;s answers combine into results and logs on the website.</desc>
    <Arrows id="run-arrow" />
    <Edge d="M340 124H497" id="run-arrow" /><text className="edge-label" x="420" y="104" textAnchor="middle">sends transactions</text>
    <Edge d="M980 124H823" id="run-arrow" /><text className="edge-label" x="900" y="104" textAnchor="middle">reads the chain state</text>
    <text className="diagram-caption" x="660" y="260" textAnchor="middle">Three separate containers. The agent can&apos;t reach the scorer.</text>
    <Edge d="M180 218V307" id="run-arrow" /><text className="edge-label" x="196" y="278">transcript</text>
    <Edge d="M1140 218V307" id="run-arrow" /><text className="edge-label" x="1156" y="278">checks</text>
    <Edge d="M340 377H497" id="run-arrow" /><Edge d="M820 377H977" id="run-arrow" />
    {nodes.map((node) => <DiagramNode key={node.id} node={node} />)}
  </svg>;
}
