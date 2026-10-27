Our depositors hold USDC and haven't approved anything. Let them sign once from our
page, and our keeper deposits it into our vault for them, with the shares going to the depositor.
People may sign a few now and we fill them later, and some depositors are Safes. Put the KeeperDeposits contract in
src/KeeperDeposits.sol; we'll deploy it with forge create, nothing to pass in, and it's for mainnet.
In script/deposits.ts, export prepareDeposit({ contract, depositor, amount }), returning the typed data
the depositor signs and a keeperTx(signature) that gives our keeper's { to, data }.

amount is a bigint in USDC base units (6 decimals), and contract and depositor are addresses.
prepareDeposit can be async. Return { typedData, keeperTx }, with typedData in viem's signTypedData
format (domain, types, primaryType, message). The RPC URL is in RPC_URL. chain_context.json has the
vault's address and a funded account with USDC and no approvals for your own testing.
