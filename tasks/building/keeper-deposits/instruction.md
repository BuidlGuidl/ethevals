our depositors hold USDC and haven't approved anything. let them sign once from our page, and our
keeper deposits it into our vault at 0xBc65ad17c5C0a2A4D159fa5a503f4992c7B545FE for them, shares to the
depositor. people may sign a few now and we fill them later. some depositors are Safes. put the contract
in src/KeeperDeposits.sol, we'll deploy it with forge create, nothing to pass in; it's for mainnet. in
script/deposits.ts, export prepareDeposit({ contract, depositor, amount }), returning the typed data the
depositor signs and a keeperTx(signature) that gives our keeper's { to, data }.

amount is a bigint in USDC base units (6 decimals). contract and depositor are addresses.
prepareDeposit can be async. return { typedData, keeperTx }, with typedData in viem's signTypedData
format (domain, types, primaryType, message). the RPC URL is in RPC_URL. chain_context.json has a funded
account with USDC and no approvals for your own testing.
