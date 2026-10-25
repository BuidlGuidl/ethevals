# Keeper deposits

A team asks for one-signature USDC deposits paid for by its keeper.
The task checks pending deposits, signatures submitted before the keeper call, and deposits from a real Safe.

## The instruction

> Hi, quick one: our depositors hold USDC and haven't approved anything. Let them sign once from our
> page, and our keeper deposits it into our vault for them, with the shares going to the depositor.
> People may sign a few now and we fill them later, and some depositors are Safes. Put the contract in
> src/KeeperDeposits.sol; we'll deploy it with forge create, nothing to pass in, and it's for mainnet.
> In script/deposits.ts, export prepareDeposit({ contract, depositor, amount }), returning the typed data
> the depositor signs and a keeperTx(signature) that gives our keeper's { to, data }.
>
> amount is a bigint in USDC base units (6 decimals), and contract and depositor are addresses.
> prepareDeposit can be async. Return { typedData, keeperTx }, with typedData in viem's signTypedData
> format (domain, types, primaryType, message). The RPC URL is in RPC_URL. chain_context.json has the
> vault's address and a funded account with USDC and no approvals for your own testing.

## What it touches

- USDC authorizations. A permit grants an allowance; it does not complete the deposit. Another account can submit it first.
- Pending signatures. Reading the token's current sequential nonce twice can produce two signatures for the same nonce.
- Contract signatures. A Safe asked to sign typed data from a page returns an ERC-1271 signature over that typed data, built from its owners' signatures. A design that needs owners to sign a Safe transaction has nothing the page can hand it. USDC's bytes overloads support ERC-1271 validation.

## The checks

The verifier rebuilds the submitted source with FFI disabled, imports the helper, and deploys the contract without constructor arguments.
It runs each check on a private fork with fresh depositors and a separate funded keeper.

- The environment has Foundry, Solidity 0.8.30, Node 22, viem, TypeScript, and tsx.
- Its chain forks Ethereum mainnet at block 23,819,000 and gives the agent a funded account with USDC and no approvals.

| Check | What it proves | Instruction sentence | Area |
| --- | --- | --- | --- |
| `compile` | The contract builds and the helper returns signable typed data and a keeper transaction | "export prepareDeposit" | interface |
| `deposit_lands` | One EOA signature lets the keeper deposit the exact amount and gives the depositor at least the shares the vault previews at the mined block | "let them sign once from our page, and our keeper deposits it into our vault ... shares to the depositor" | deposit |
| `signature_used_first` | Submitting the signed token authorization before the keeper call still leaves the depositor with the shares and no contract residue | "our keeper deposits it into our vault ... for them" | front-run |
| `two_pending` | Two deposits prepared and signed before either fill both land in signing order | "people may sign a few now and we fill them later" | nonces |
| `safe_depositor` | Two owners of a real 2-of-3 Safe sign its SafeMessage digest and the keeper deposits the Safe's USDC | "some depositors are Safes" | signatures |
| `no_replay` | Repeating a filled keeper transaction moves no USDC or shares | "let them sign once" | replay |

How the checks judge:

- Every positive deposit checks the exact USDC debit, the depositor's shares, and zero USDC and shares left in the contract.
- The keeper supplies no USDC and receives no shares.
- A reverted keeper transaction fails a positive check and counts as no movement on the replay check.
- The replay check counts only after `deposit_lands` passes.
- The reward is 1 only when every check passes.

## Why it matters

[OpenZeppelin's IERC20Permit comment](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/contracts/token/ERC20/extensions/IERC20Permit.sol#L16-L40) describes permit front-running and fault-tolerant permit calls.
It also recommends entry points that do not require permits for contract wallets.
[ERC-3009](https://eips.ethereum.org/EIPS/eip-3009) describes random nonces and a receive authorization restricted to the payee.
That restriction lets a contract receive tokens and use them in one transaction.

[Circle's FiatTokenV2_2](https://github.com/circlefin/stablecoin-evm/blob/master/contracts/v2/FiatTokenV2_2.sol) implements bytes-signature overloads for permits and transfer authorizations.
[Universal Router](https://github.com/Uniswap/universal-router/blob/edf19bfde87e6cf5b29046f6ca2f483a4ffd6ae6/contracts/UniversalRouter.sol#L82-L96) lets callers tolerate failures of selected commands.
The [Puffer Finance report on Immunefi](https://reports.immunefi.com/puffer-finance/28702-sc-insight-malicious-users-can-frontrun-permits-to-dos-swaps) records a permit front-running griefing report.
These sources explain why a token authorization's success and the full operation's success need separate handling.

## Notes

- The solution uses USDC's bytes `receiveWithAuthorization` overload and Spark's sUSDC vault. It chooses random 32-byte nonces and a deadline seven days after the chain timestamp. Depositors make no approval transaction.
- The Safe fixture deploys Safe 1.4.1 through its real factory with the compatibility fallback handler.
- For the prior-submission check, `Permit`, `TransferWithAuthorization`, and `ReceiveWithAuthorization` typed data select their USDC bytes overloads. A different typed-data type has no corresponding USDC entry point, so that check submits no token call before the keeper transaction.
- The prior-submission check accepts a failed prior submission and still requires a successful deposit.
- The checks fix no calldata layout, storage scheme, or nonce scheme.
