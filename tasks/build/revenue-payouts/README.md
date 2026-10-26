# Revenue payouts

A team launching an NFT collection asks for a contract that splits its income by share.
Mint money arrives as ETH, and partners pay in USDC and USDT.
The instruction names the contract's interface and nothing more.
Hidden Forge tests then check the gotchas that any contract holding and sending money runs into.

The task comes from the Payment Splitter idea in BuidlGuidl's [build prompts](https://speedrunethereum.com/build-prompts).
It drops the factory and the frontend, and adds the ERC-20 splitting that the build prompt lists as its next step.

## The instruction

```text
we're launching an NFT collection with a few collaborators and want the money split between us by
share. mint money comes in as ETH, and some partners pay us in stablecoins like USDC and USDT.
can you write a contract we can use as the payout address? put it in src/RevenuePayouts.sol as a
contract called RevenuePayouts. the constructor takes (address[] payees, uint256[] shares). anyone can
call release(payeeAddress) to send a payee the ETH they're owed so far, and
release(tokenAddress, payeeAddress) for tokens. it's a Foundry project on solidity 0.8.30.
```

## What it touches

The task touches three areas that come up in almost every Ethereum app. The instruction mentions none of their gotchas.

- **Stablecoins as they behave on mainnet.** USDT's `transfer` returns nothing, so a contract that expects a `bool` reverts. USDC can freeze an address, and one frozen payee mustn't block the rest. No code runs when tokens arrive, so the contract has to read its own balance.
- **Sending ETH to addresses you don't control.** A payee can be a contract or a smart wallet. It can reject ETH, need more than the [2,300 gas](https://docs.soliditylang.org/en/v0.8.30/security-considerations.html) that `transfer` and `send` forward, or call back in while it's being paid.
- **Accounting while money keeps arriving.** A payee is owed its share of everything received so far, minus what it already took. Paying `balance * share / total` goes wrong as soon as anyone has released.

## The checks

The agent starts with a Foundry project on Solidity 0.8.30 that holds only `foundry.toml`.
When it stops, the verifier puts the agent's project next to [`RevenuePayouts.t.sol`](tests/RevenuePayouts.t.sol) and runs Forge.
Each test is one check, and the reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contract compile together | all |
| `test_usdtNoReturn` | USDT can be released, though its `transfer` returns nothing | stablecoins |
| `test_laterTokens` | Tokens sent by plain transfer, with more arriving after a release, still split exactly | stablecoins |
| `test_frozenUSDCPayee` | A payee frozen by USDC doesn't stop the others claiming | stablecoins |
| `test_rejectingPayee` | A payee that rejects ETH doesn't block the others | sending ETH |
| `test_gasHungryPayee` | A payee whose `receive` needs more than 2,300 gas still gets paid | sending ETH |
| `test_reentrantPayee` | A payee that calls `release` again while being paid gets no more than its share | sending ETH |
| `test_laterETH` | One payee releases, another 1 ETH arrives, then everyone releases. Each ends with exactly their share of 2 ETH | accounting |
| `test_noDoublePayment` | A second release with nothing new owed pays nothing | payouts |
| `test_assetLedgers` | Releasing a token doesn't change what's owed in ETH | payouts |
| `test_strangerRelease` | A stranger calling `release(B)` pays B, and the stranger gets nothing | payouts |
| `test_rounding` | With shares of 33, 33 and 34 and 101 wei in, each first release pays its share rounded down | payouts |
| `test_constructorValidation` | Mismatched lists, a zero share, or the zero address make the constructor revert | payouts |

## Why it matters

The same gotchas show up well beyond splitting.
Uniswap V2 wraps token transfers in [`_safeTransfer`](https://github.com/Uniswap/v2-core/blob/v1.0.1/contracts/UniswapV2Pair.sol) because of tokens like USDT.
[Lendf.me lost about $25M](https://quantstamp.com/blog/how-the-dforce-hacker-used-reentrancy-to-steal-25-million) to reentrancy through a token callback.
Staking contracts like [StakingRewards](https://github.com/Uniswap/liquidity-staker/blob/v1.0.2/contracts/StakingRewards.sol) keep the same running totals as a payout contract.

## Notes

- The tests put mock USDC and USDT at the real mainnet addresses, so the task needs no RPC. An agent that hardcodes the two addresses still passes.
- The mocks copy the behavior that matters. USDT's `transfer` returns nothing, and USDC reverts a transfer from or to a frozen address.
- The tests call only the constructor, the two `release` functions, and plain transfers, and they accept any revert. The agent's own error and event names don't matter.
- OpenZeppelin 4.9's [PaymentSplitter](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v4.9.6/contracts/finance/PaymentSplitter.sol) passes every test, so an agent that reaches for it passes. OpenZeppelin 5 removed it.
