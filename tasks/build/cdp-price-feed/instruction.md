We're building a CDP stablecoin for mainnet, one collateral branch each for WETH, wstETH and rETH.
Our TroveManager and BorrowerOperations are done and talk to each branch's price feed through
src/interfaces/IPriceFeed.sol: fetchPrice() for opening, adjusting and liquidating Troves,
fetchRedemptionPrice() for redemptions, both in USD with 18 decimals, and when either call reports
the oracle as broken, BorrowerOperations stops new borrowing on that branch while liquidations and
closes keep going on the price you return. Use Chainlink. Redemptions get their own price because
redeemers take collateral at it, and we don't want them picking up our borrowers' LST collateral
cheap when it trades a little under its staking rate. Put the feeds in src/PriceFeeds/ and a deploy
script in script/DeployPriceFeeds.s.sol as DeployPriceFeeds, whose run() returns the WETH, wstETH
and rETH feed addresses, in that order; it should deploy against mainnet as is, so bake the
addresses in. we're on foundry with solidity 0.8.30.
