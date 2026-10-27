We're building a launchpad for community tokens. anyone calls create(name, symbol), which
returns a new token with a 1B supply that sells on a bonding curve: buy(token) pays ETH for tokens,
and sell(token, amount) sells them back for ETH. the token's creator earns 1% of every curve trade
and claims it with claimFees(token). once a curve has taken in 10 ETH, anyone can call
graduate(token), which puts the curve's ETH and as many tokens as it needs into a Uniswap v2 pool
against WETH, opening at the curve's last price, and burns the LP. could you put it in
src/Launchpad.sol as a contract called Launchpad, deployed with no constructor arguments? it's a
Foundry project on solidity 0.8.30, for mainnet.
