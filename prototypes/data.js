/* Fake benchmark data. Four views of one deterministic dataset. */
(function () {
  "use strict";
  const agents = [
    { id: "opus", name: "Opus 5.5", harness: "Claude Code", effort: "high" },
    { id: "fable", name: "Fable 5.1", harness: "Claude Code", effort: "high" },
    { id: "sonnet", name: "Sonnet 5", harness: "Claude Code", effort: "medium" },
    { id: "astra", name: "GPT-6 Astra", harness: "Codex", effort: "medium" },
    { id: "glm", name: "GLM 5.3", harness: "OpenCode", effort: "default" },
    { id: "kimi", name: "Kimi K3", harness: "OpenCode", effort: "default" },
    { id: "deepseek", name: "DeepSeek V4", harness: "pi", effort: "default" }
  ];
  const modes = [
    { id: "vanilla", name: "Vanilla", short: "V", description: "No internet" },
    { id: "internet", name: "Internet", short: "I", description: "Open web, no skills" },
    { id: "skills", name: "Skills", short: "S", description: "Internet + ethskills" }
  ];
  const pillars = [
    { id: "concepts", name: "Concepts", description: "Explain, choose, judge a claim" },
    { id: "transactions", name: "Transactions", description: "Read state, decode, build calldata, send" },
    { id: "building", name: "Building", description: "Contracts, tests, a page, a repair" },
    { id: "security", name: "Security", description: "Audit, exploit and patch, prove a fix" }
  ];
  // id, title, pillar, task type, grader, supports Vanilla
  const definitions = [
    ["concepts-k-06", "Finality vs confirmations", "concepts", "Quiz", "deterministic", true],
    ["gas-basefee-01", "Next-block base fee under EIP-1559", "concepts", "Quiz", "deterministic", true],
    ["l2s-k-03", "Optimistic vs ZK withdrawal delay", "concepts", "Quiz", "deterministic", true],
    ["erc-8004-quiz", "Which ERC defines trustless agents?", "concepts", "Quiz", "deterministic", true],
    ["latest-eip-live", "EIPs shipped in the latest fork", "concepts", "Quiz", "judge", false],
    ["wallets-quiz-002", "Custody for an unattended signing bot", "concepts", "Scenario", "judge", true],
    ["l2s-quiz-002", "Choose an L2 for a payments app", "concepts", "Scenario", "judge", true],
    ["calldata-sel-05", "Function selector from a signature", "transactions", "Quiz", "deterministic", true],
    ["tx-calldata-permit-2612", "EIP-2612 permit calldata", "transactions", "Quiz", "deterministic", true],
    ["live-pool-liquidity", "WETH in the USDC/WETH 0.05% pool", "transactions", "Act", "chain state", false],
    ["proto-blob-base-fee", "Current blob base fee", "transactions", "Act", "chain state", false],
    ["swap-calldata-01", "Uniswap swap on a pinned fork", "transactions", "Act", "tests", false],
    ["tx-eip1559-transfer", "Send a type-2 transfer on anvil", "transactions", "Act", "chain state", false],
    ["erc20-oz", "Build an ERC-20 with OpenZeppelin", "building", "Build", "judge", false],
    ["dca-contract-01", "DCA contract", "building", "Build", "tests", false],
    ["lp-rebalance-01", "LP range rebalancer", "building", "Build", "tests", false],
    ["repo-repair", "Fix a broken Foundry repo", "building", "Build", "tests", false],
    ["testing-goal-001", "Fuzz + invariant suite for a vault", "building", "Build", "tests", false],
    ["frontend-ux-goal-002", "Approve-then-swap button flow", "building", "Build", "judge", false],
    ["security-k-08", "Reentrancy guard ordering", "security", "Quiz", "deterministic", true],
    ["audit-quiz-002", "Triage audit findings", "security", "Scenario", "judge", true],
    ["security-goal-001", "Audit a staking contract", "security", "Scenario", "judge", false],
    ["vault-exploit-patch", "Exploit then patch a vault", "security", "Act", "chain state", false],
    ["dvd-puppet", "Damn Vulnerable DeFi oracle drain", "security", "Act", "chain state", false],
    ["fix-vault-01", "Patch proven by a Foundry test", "security", "Build", "tests", false]
  ];
  function hash(text) {
    let value = 2166136261;
    for (let i = 0; i < text.length; i++) value = Math.imul(value ^ text.charCodeAt(i), 16777619);
    return value >>> 0;
  }
  const clamp = value => Math.max(0, Math.min(100, value));
  const missing = new Set([
    "latest-eip-live:kimi:internet", "latest-eip-live:deepseek:skills",
    "lp-rebalance-01:glm:skills", "repo-repair:sonnet:internet",
    "dvd-puppet:fable:skills", "tx-eip1559-transfer:deepseek:internet",
    "erc-8004-quiz:astra:vanilla", "security-k-08:kimi:vanilla"
  ]);
  const strength = {
    concepts: [55, 54, 45, 52, 39, 37, 35],
    transactions: [40, 42, 32, 41, 23, 26, 22],
    building: [49, 48, 39, 47, 31, 29, 32],
    security: [40, 43, 32, 38, 26, 25, 23]
  };
  const checks = {
    deterministic: ["Expected answer", "Numeric precision", "Required fields", "Boundary case"],
    tests: ["Compiles", "Happy path", "Failure path", "Invariant"],
    "chain state": ["Transaction receipt", "Balance delta", "Event log", "Final state"]
  };
  const evals = definitions.map(([id, title, pillar, type, grader, vanilla]) => {
    const evaluation = {
      id, title, pillar, type, grader,
      modes: vanilla ? ["vanilla", "internet", "skills"] : ["internet", "skills"],
      prompt: `${title}. Use the supplied fixture. Return your answer and evidence for the grader.`,
      results: {}
    };
    agents.forEach((agent, agentIndex) => {
      evaluation.results[agent.id] = {};
      const seed = hash(`${id}:${agent.id}`);
      let base = strength[pillar][agentIndex] + (hash(id) % 19 - 9) + (seed % 11 - 5);
      if (id === "calldata-sel-05" && agent.id === "deepseek") base = 13;
      const lift = seed % 13 === 0 ? -(seed % 4) : 5 + seed % 26;
      modes.forEach(mode => {
        // null = not applicable; an empty runs array = supported, no run yet.
        if (!evaluation.modes.includes(mode.id)) {
          evaluation.results[agent.id][mode.id] = null;
          return;
        }
        const result = { runs: [] };
        evaluation.results[agent.id][mode.id] = result;
        if (missing.has(`${id}:${agent.id}:${mode.id}`)) return;
        const target = base + (mode.id === "skills" ? lift : mode.id === "vanilla" ? -(6 + seed % 12) : 0);
        const count = 3 + seed % 3;
        for (let i = 0; i < count; i++) {
          const noise = (i - (count - 1) / 2) * (5 + seed % 5);
          const raw = clamp(Math.round(target + noise));
          const score = grader === "judge" ? raw : Math.round(raw / 5) * 5;
          const passedChecks = score / 5;
          const rubric = [
            { name: "Correctness", score },
            { name: "Completeness", score: clamp(score - 6) },
            { name: "Evidence", score: clamp(score + 6) }
          ];
          // Targets stay away from the endpoints for judge runs, so the rubric mean equals the score.
          const runScore = grader === "judge" ? rubric.reduce((sum, item) => sum + item.score, 0) / rubric.length : score;
          const input = 1400 + seed % 5200 + i * 143;
          const output = 350 + seed % 1800 + i * 81;
          const isBuild = type === "Build" || type === "Act";
          result.runs.push({
            id: `${id}:${agent.id}:${mode.id}:${i + 1}`,
            score: runScore,
            pass: runScore >= 60,
            cost: Number(((input + output * 3) * [0.000003, 0.0000025, 0.0000015, 0.000002, 0.0000006, 0.0000005, 0.0000004][agentIndex]).toFixed(4)),
            tokens: { input, output },
            durationSec: 18 + seed % (isBuild ? 220 : 65) + i * 9 + (mode.id === "skills" ? 14 : 0),
            transcript: [
              `[00:00] Task: ${id}`,
              mode.id === "vanilla" ? "[00:02] Tools: local fixture only. Web access disabled." : "[00:02] Read fixture and mock reference snapshot.",
              mode.id === "skills" ? "[00:05] Read ethskills guidance for this task." : "[00:05] Plan answer from available context.",
              `[00:12] ${isBuild ? "Write patch and run fixture checks." : "Submit answer with supporting evidence."}`,
              `[done] Grader score: ${Math.round(runScore)} / 100. ${runScore >= 60 ? "Pass" : "Fail"}.`
            ],
            files: isBuild ? ["src/Task.sol", "test/Task.t.sol", "artifacts/result.json"] : ["answer.md", "artifacts/result.json"],
            diff: isBuild ? "--- src/Task.sol\n+++ src/Task.sol\n-    execute(amount);\n+    require(amount > 0);\n+    execute(amount);" : "--- answer.md\n+++ answer.md\n+ Answer from the supplied fixture.\n+ Evidence and assumptions attached.",
            grader: grader === "judge" ? {
              kind: "judge", rubric,
              note: runScore >= 60 ? "Core answer holds. Evidence covers most rubric items." : "Partial answer. Missing evidence and edge cases reduce the score."
            } : {
              kind: grader,
              checks: Array.from({ length: 20 }, (_, index) => ({
                name: `${checks[grader][index % 4]} · fixture ${Math.floor(index / 4) + 1}`,
                pass: index < passedChecks
              }))
            }
          });
        }
      });
    });
    return evaluation;
  });
  window.EVALS = { agents, modes, pillars, evals, passThreshold: 60, fixture: "Synthetic results · fixed seed" };
})();
