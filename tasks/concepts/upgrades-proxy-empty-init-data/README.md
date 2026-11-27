# Proxy created with empty init data

A team asks who owns their vault after a deploy script creates an `ERC1967Proxy` with empty data and calls `initialize` in a second transaction.
On OpenZeppelin Contracts 5.7.0, the release in the repo's lock file, the proxy constructor reverts, so nothing is deployed.
The task checks whether the reply says so.

## The instruction

> We set up a fresh Foundry repo for our vault this week. `foundry.lock`:
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
>   },
>   "lib/openzeppelin-contracts-upgradeable": {
>     "tag": {
>       "name": "v5.7.0",
>       "rev": "14f52c54d3a1eefbda3d4071efba24d3c1e07e8a"
>     }
>   }
> }
> ```
>
> `Vault` is a plain UUPS vault. Its `initialize(address owner_)` is an `initializer` that calls `__Ownable_init(owner_)`.
>
> `script/Deploy.s.sol`:
>
> ```solidity
> function run() external {
>     vm.startBroadcast();
>     Vault impl = new Vault();
>     ERC1967Proxy proxy = new ERC1967Proxy(address(impl), "");
>     Vault(address(proxy)).initialize(MULTISIG);
>     vm.stopBroadcast();
> }
> ```
>
> We run it against mainnet tomorrow. After the script finishes, who owns the vault at the proxy address? Answer, then explain in one or two sentences.

## What it touches

The instruction shows the repo's `foundry.lock`, which holds OpenZeppelin Contracts 5.7.0, and says nothing else about versions.
The reply has to read the release from it and know, or look up, what that release does.
Since OpenZeppelin Contracts 5.6.0, `ERC1967Proxy` and `TransparentUpgradeableProxy` revert with `ERC1967ProxyUninitialized` when the data argument is empty.
Before 5.6.0 the same script deployed an uninitialized proxy, and the usual review comment was that anyone could call `initialize` first.
That older answer names the multisig or a front-runner as the owner, and both are wrong for this repo.

## The checks

A judge reads the question, the right answer, and the final reply, and nothing else.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `proxy_creation_reverts` | The judge finds that proxy creation reverts and no vault is deployed | Upgrades |

The task runs in vanilla, internet, and skills modes.

## Why it matters

A deploy script written for an older release stops working after a dependency update, and a review that still describes the old behaviour sends the team looking for a front-running fix they no longer need.
The [OpenZeppelin Contracts changelog](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/CHANGELOG.md#560-2026-02-25) lists the change under 5.6.0, from [pull request 5906](https://github.com/OpenZeppelin/openzeppelin-contracts/pull/5906).

## Notes

A Foundry test against OpenZeppelin Contracts 5.7.0 confirms the revert, with selector `0xc28a273c`.
The lock file in the instruction is the one `forge install` wrote in a fresh repo on 2026-11-25.
It fixes the release, so the right answer stays the same when a later release ships.
The judge is the board's judge, Claude Opus 5.5 at high effort, and it reads only the question, the right answer, and the final reply.
`tests/hand-cases.json` holds right and wrong replies with their correct marks.
