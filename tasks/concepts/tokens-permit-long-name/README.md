# Permit token with a long name

A team asks whether permit signatures from their frontend will be accepted by a new token whose name is 33 bytes long.
On OpenZeppelin Contracts 5.7.0, the release in the repo's lock file, the token's constructor reverts, so nothing is deployed.
The task checks whether the reply says so.

## The instruction

> We set up a fresh Foundry repo for our governance token this week. `foundry.lock`:
>
> ```json
> {
>   "lib/forge-std": {
>     "tag": {
>       "name": "v1.17.0",
>       "rev": "f3dae6e6ee381f25eb6a246f7da9b85c91a68219"
>     }
>   },
>   "lib/openzeppelin-contracts": {
>     "tag": {
>       "name": "v5.7.0",
>       "rev": "cab19933c33c2ad1d4c7a84864a3601dddfd16f3"
>     }
>   }
> }
> ```
>
> `src/Token.sol`:
>
> ```solidity
> contract Token is ERC20, ERC20Permit {
>     constructor(address treasury)
>         ERC20("Lantern Protocol Governance Token", "LPG")
>         ERC20Permit("Lantern Protocol Governance Token")
>     {
>         _mint(treasury, 10_000_000e18);
>     }
> }
> ```
>
> Our frontend signs permits with the domain name `Lantern Protocol Governance Token` and version `1`. We deploy to mainnet tomorrow. Will the token accept those permit signatures? Answer, then explain in one or two sentences.

## What it touches

The instruction shows the repo's `foundry.lock`, which holds OpenZeppelin Contracts 5.7.0, and says nothing else about versions.
The reply has to read the release from it and know, or look up, what that release does.
Since OpenZeppelin Contracts 5.7.0, the `EIP712` constructor reverts with `ShortStrings.StringTooLong` when the name or version is longer than 31 bytes.
Before 5.7.0 a longer name was kept in storage, and the same token deployed and accepted the signatures.
`ERC20Permit`, `ERC20Votes`, and `Governor` all pass a name to that constructor.

## The checks

A judge reads the question, the right answer, and the final reply, and nothing else.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `token_deploy_reverts` | The judge finds that the token deployment reverts because the name is over 31 bytes | Tokens |

The task runs in vanilla, internet, and skills modes.

## Why it matters

A token name a few letters over the limit stops a deployment that worked on the release before.
A review that only compares the domain fields tells the team the signatures are fine, for a token that cannot be deployed.
The [OpenZeppelin Contracts changelog](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/CHANGELOG.md#570-2026-07-29) lists the change under 5.7.0, from [pull request 6631](https://github.com/OpenZeppelin/openzeppelin-contracts/pull/6631).

## Notes

A Foundry test against OpenZeppelin Contracts 5.7.0 confirms it: a 31-byte name deploys, and a 33-byte name reverts with `StringTooLong`.
The lock file entries in the instruction are the ones `forge install` wrote in a fresh repo on 2026-11-25.
They fix the release, so the right answer stays the same when a later release ships.
The judge is the board's judge, Claude Opus 5.5 at high effort, and it reads only the question, the right answer, and the final reply.
`tests/hand-cases.json` holds right and wrong replies with their correct marks.
