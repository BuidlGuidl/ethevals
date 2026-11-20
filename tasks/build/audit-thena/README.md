# THENA audit

The agent audits THENA's contracts at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each Critical and High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/retro-thena-audit), one question per finding.

## The instruction

> You are a smart contract security auditor auditing THENA. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> THENA is a ve(3,3) exchange on BNB Chain in the Solidly family, with stable, volatile and concentrated-liquidity pools. Liquidity providers stake their LP tokens in each pool's gauge to earn weekly THE emissions, and holders of locked veTHE vote every week on how those emissions are split between gauges, earning the pools' fees and bribes in return. The voter, the minter, the gauges and their extra-reward contracts run this weekly cycle.

## What it touches

The image clones [ThenafiBNB/THENA-Contracts](https://github.com/ThenafiBNB/THENA-Contracts) at `2bb84cf6bb429e9bac8ac8464f4546da855ef4ca`, the commit the audit names.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`contracts/` holds 82 files and about 12,900 lines. The audit covered five of them: `VoterV3.sol`, `GaugeV2.sol`, `GaugeV2_CL.sol`, `GaugeExtraRewarder.sol` and `PermissionsRegistry.sol`. The findings also reach into `MinterUpgradeable.sol`.
The project builds with Hardhat and pulls its libraries with npm. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but it does not install the project's packages, so the agent has to run `npm install` itself. It has the web. Its `.gitmodules` lists Foundry libraries, but the commit pins none, so `lib/` is not there.

All five findings follow one week's emissions, or one retired gauge, through the minter, the voter and the gauges:

- **Two ways to start a week.** The voter's distribute functions start the new week and pay out the old one together, but anyone can also start it on the minter alone. The auditor has to see which week's votes the voter reads in between.
- **A period that never ends.** The extra-rewards contract is funded for a week. The auditor has to see that its accrual keeps running after that.
- **Votes that stay counted.** Killing a gauge stops its payouts. The auditor has to check what happens to the votes it already had in the week's total.
- **Votes for a dead gauge.** The auditor has to see that voting checks that a gauge exists, not that it is alive.
- **A half-deleted gauge.** Killing a gauge for good deletes its bribe contracts and, through an ordering slip, fails to clear the pool's gauge. The auditor has to follow a past voter's next vote into those deleted records.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_period_update_erases_rewards` | The report finds C-1: after a direct `update_period`, `_updateFor` reads the new week's empty votes, so a tiny vote on every gauge erases the finished week's rewards | weekly emissions |
| `h1_extra_rewarder_past_period` | The report finds H-1: the extra rewarder keeps accruing after its funded period, so some stakers take others' rewards and the gauge can revert | extra rewards |
| `h2_killed_gauge_votes_stay_in_total` | The report finds H-2: killing a gauge leaves its votes in the week's total, so its share of emissions is stuck in the voter | gauge kill |
| `h3_vote_for_killed_gauge` | The report finds H-3: voting checks `isGauge` but not `isAlive`, so votes for a killed gauge lock emissions | voting |
| `h4_total_kill_locks_voters` | The report finds H-4: `killGaugeTotally` clears the bribes but not the voters' records or `gauges[pool]`, so those voters' next vote reverts | gauge kill |

## Why it matters

In a ve(3,3) exchange the weekly emissions are what pay liquidity providers, so a flaw that loses or locks a week of them hurts every pool at once.
OpenZeppelin's [Retro/Thena audit](https://www.openzeppelin.com/news/retro-thena-audit) (June 2023) found these five flaws, and the project fixed them:

- C-1 in [ThenafiBNB/THENA-Contracts#2](https://github.com/ThenafiBNB/THENA-Contracts/pull/2).
- H-1 to H-4 in [ThenafiBNB/THENA-Contracts#3](https://github.com/ThenafiBNB/THENA-Contracts/pull/3). H-2 was fixed for the current week only; the team said its own procedures distribute right after each period update.

## Notes

The audit also lists Medium and Low findings. The task checks only the Critical and the four Highs, and other true findings in the report don't fail it.
The instruction names all of `contracts/`, which is much larger than the five files the audit covered, so agents may report real bugs elsewhere. Those take report slots but don't fail a trial.
H-2 and H-4 start with governance killing a gauge, an action the protocol expects to take against malicious gauges. The harm falls on voters and on the emissions, not on the role that acts.
It's a 2023 report on a well-known ve(3,3) fork, so models may remember it.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
