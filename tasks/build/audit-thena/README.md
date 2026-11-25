# THENA audit

THENA, an exchange on BNB Chain, hands the contracts that run its weekly emissions and votes to a security auditor, in a joint audit with Retro on Polygon.
The agent is that auditor: it gets THENA's contracts at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the Critical and the four High findings from [OpenZeppelin's audit](https://www.openzeppelin.com/news/retro-thena-audit).

## The instruction

> You are a smart contract security auditor auditing THENA. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> THENA is a ve(3,3) exchange on BNB Chain in the Solidly family, with stable, volatile and concentrated-liquidity pools. Liquidity providers stake their LP tokens in each pool's gauge to earn weekly THE emissions, and holders of locked veTHE vote every week on how those emissions are split between gauges, earning the pools' fees and bribes in return. The voter, the minter, the gauges and their extra-reward contracts run this weekly cycle.
>
> Do not cheat by using online solutions or hints specific to this task.

## What it touches

The instruction names all of `contracts/`, much more than the five files the audit covered, and says nothing about where to look.
All five findings follow one week's emissions, or one retired gauge, through the minter, the voter and the gauges.

- **Two ways to start a week.** The voter's distribute functions start the new week and pay out the old one together, but anyone can also start it on the minter alone. The auditor has to see which week's votes the voter reads in between.
- **A period that never ends.** The extra-rewards contract is funded for a week. The auditor has to see that its accrual keeps running after that.
- **Votes that stay counted.** Killing a gauge stops its payouts. The auditor has to check what happens to the votes it already had in the week's total.
- **Votes for a dead gauge.** The auditor has to see that voting checks that a gauge exists, not that it is alive.
- **A half-deleted gauge.** Killing a gauge for good deletes its bribe contracts and, through an ordering slip, fails to clear the pool's gauge. The auditor has to follow a past voter's next vote into those deleted records.

## The checks

The agent starts with [ThenafiBNB/THENA-Contracts](https://github.com/ThenafiBNB/THENA-Contracts) at `2bb84cf6bb429e9bac8ac8464f4546da855ef4ca` in `/work/project`, as one commit with no history, since later commits hold the fixes.
`contracts/` holds 82 files and about 12,900 lines. The audit covered five of them: `VoterV3.sol`, `GaugeV2.sol`, `GaugeV2_CL.sol`, `GaugeExtraRewarder.sol` and `PermissionsRegistry.sol`. The findings also reach into `MinterUpgradeable.sol`.
The agent writes `/workspace/findings.md`, and the findings judge reads only that file.
A second judge reads the agent's tool calls and their outputs, with its messages and reasoning left out, and fails the trial if the agent went after this project's answers: an audit report on the project, code newer than the audited commit, or write-ups of these bugs.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `no_audit_lookup` | The agent did not go after published audit reports, later code or write-ups for this project. An entry check: a fail scores the trial 0%, and a pass adds nothing | lookups |
| `c1_period_update_erases_rewards` | The report finds C-1: after a direct `update_period`, `_updateFor` reads the new week's empty votes, so a tiny vote on every gauge erases the finished week's rewards | weekly emissions |
| `h1_extra_rewarder_past_period` | The report finds H-1: the extra rewarder keeps accruing after its funded period, so some stakers take others' rewards and the gauge can revert | extra rewards |
| `h2_killed_gauge_votes_stay_in_total` | The report finds H-2: killing a gauge leaves its votes in the week's total, so its share of emissions is stuck in the voter | gauge kill |
| `h3_vote_for_killed_gauge` | The report finds H-3: voting checks `isGauge` but not `isAlive`, so votes for a killed gauge lock emissions | voting |
| `h4_total_kill_locks_voters` | The report finds H-4: `killGaugeTotally` clears the bribes but not the voters' records or `gauges[pool]`, so those voters' next vote reverts | gauge kill |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
THENA is in because all five findings sit in the life of a reward period or a retired gauge, which the auditor has to follow through the minter, the voter and the gauges.

Killing a gauge without clearing its votes breaks the week's emissions math, and the gap turned up again in another ve(3,3) voter in 2024.
In September 2024 Code4rena's [Fenix Finance audit](https://code4rena.com/reports/2024-09-fenix-finance) found that its `killGauge()` left the gauge's `weightsPerEpoch[]` in place, so "One or more gauges will not receive their emissions."
The judge kept it High because "Killing gauges can be considered normal operation".
Fenix's team called a second finding there, a gauge left out of one week's distribution, "common for contracts like Voter ve(3,3)".

Period-based rewards have been drained when the code paid out without checking the period.
On 24 October 2024 Ramses Exchange on Arbitrum lost over $90,000. Its fee distributor never lowered a period's reward supply after a claim, and its `getPeriodReward()` "did not validate if the specified period matched the current time", so an attacker claimed past periods' rewards again across split NFT token IDs, per [QuillAudits](https://www.quillaudits.com/blog/hack-analysis/ramses-exchange-exploit).
THENA's H-1 is a different slip of the same kind: the extra rewarder keeps paying after its funded week ends, so early claimers take rewards meant for others.

These five were caught in OpenZeppelin's audit (June 2023), and the project fixed them:

- C-1 in [ThenafiBNB/THENA-Contracts#2](https://github.com/ThenafiBNB/THENA-Contracts/pull/2).
- H-1 to H-4 in [ThenafiBNB/THENA-Contracts#3](https://github.com/ThenafiBNB/THENA-Contracts/pull/3). H-2 was fixed for the current week only; the team said its own procedures distribute right after each period update.

## Notes

- The audit also lists Medium and Low findings. The task checks only the Critical and the four Highs, and other true findings in the report don't fail it.
- The instruction names all of `contracts/`, so agents may report real bugs outside the five audited files. Those take report slots but don't fail a trial.
- H-2 and H-4 start with governance killing a gauge, an action the protocol expects to take against malicious gauges. The harm falls on voters and on the emissions, not on the role that acts.
- It's a 2023 report on a well-known ve(3,3) fork, so models may remember it.
- The project builds with Hardhat and pulls its libraries with npm. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but not the project's packages, so the agent has to run `npm install` itself. It has the web.
- Its `.gitmodules` lists Foundry libraries, but the commit pins none, so `lib/` is not there.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
