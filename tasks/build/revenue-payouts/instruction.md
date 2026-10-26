we're launching an NFT collection with a few collaborators and want the money split between us by
share. mint money comes in as ETH, and some partners pay us in stablecoins like USDC and USDT.
can you write a contract we can use as the payout address? put it in src/RevenuePayouts.sol as a
contract called RevenuePayouts. the constructor takes (address[] payees, uint256[] shares). anyone can
call release(payeeAddress) to send a payee the ETH they're owed so far, and
release(tokenAddress, payeeAddress) for tokens. it's a Foundry project on solidity 0.8.30.
