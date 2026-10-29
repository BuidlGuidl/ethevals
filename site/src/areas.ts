import type { Eval, Layer } from "./board";

export const domains = ["dapp-development", "security"] as const;
export type Domain = typeof domains[number];
export const domainNames: Record<Domain, string> = {
  "dapp-development": "Dapp development",
  security: "Security",
};

export const areaDomains: Readonly<Partial<Record<string, Domain>>> = {
  Agents: "dapp-development",
  Audits: "security",
  Governance: "dapp-development",
  Lending: "dapp-development",
  Payments: "dapp-development",
  Signatures: "dapp-development",
  "Smart accounts": "dapp-development",
  Swaps: "dapp-development",
  Tokens: "dapp-development",
  Wallets: "dapp-development",
};

export function taskDomain(task: Pick<Eval, "area">): Domain {
  return areaDomains[task.area ?? ""] ?? "dapp-development";
}

// Board-only tags. Tags in task.toml would change task hashes and retire every recorded trial.
// A task.toml `area` or `layer` takes precedence.
export const taskTags: Record<string, { area: string; layer?: Layer }> = {
  "act/treasury-eth-sale": { area: "Swaps" },
  "act/vault-v2-concentration-rebalance": { area: "Lending" },
  "act/vault-v2-market-exit": { area: "Lending" },
  "build/aave-savings-page": { area: "Lending", layer: "frontend" },
  "build/creator-coins": { area: "Tokens", layer: "contracts" },
  "build/keeper-deposits": { area: "Signatures", layer: "contracts" },
  "build/signed-votes": { area: "Signatures", layer: "backend" },
  "build/swap-page": { area: "Swaps", layer: "frontend" },
  "build/token-governor": { area: "Governance", layer: "contracts" },
  "build/token-launchpad": { area: "Tokens", layer: "contracts" },
  "build/token-lending-market": { area: "Lending", layer: "contracts" },
  "build/voting-page": { area: "Governance", layer: "frontend" },
  "concepts/agent-registries": { area: "Agents" },
  "concepts/governance-arbitrum-block-clock": { area: "Governance" },
  "concepts/lending-small-position-close-factor": { area: "Lending" },
  "concepts/permit2-7702-signature": { area: "Swaps" },
  "concepts/permit2-zero-expiration": { area: "Swaps" },
  "concepts/signatures-permit2-witness-string": { area: "Signatures" },
  "concepts/signatures-usdc-contract-permit": { area: "Signatures" },
  "concepts/smart-accounts-p256-precompile": { area: "Smart accounts" },
  "concepts/smart-accounts-userop-hash-v08": { area: "Smart accounts" },
  "concepts/swaps-permit2-zero-expiration": { area: "Swaps" },
  "concepts/wallet-atomic-ready": { area: "Wallets" },
  "concepts/wallet-batch-status-600": { area: "Wallets" },
};
