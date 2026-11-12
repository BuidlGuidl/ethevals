we're raffling off our community's 1/1 NFT. tickets are 0.01 ETH each, as many as you like per
wallet, and sales run for seven days from deploy. the draw has to use chainlink VRF 2.5, we have a
funded subscription. our page has a draw button for when sales close and a settle button for when
the randomness is in, and anyone can press them: settle names the winner and sends the whole pot
to our treasury without us doing anything, and the winner collects the NFT from the page. if fewer
than 100 tickets sell the raffle is off and everyone gets their ETH back. it has to run without us:
nobody should need us to get their money or the NFT, and we expect a few thousand buyers. the page
talks to it through src/interfaces/IRaffle.sol. put the raffle in src/Raffle.sol as Raffle, and a
deploy script in script/Deploy.s.sol whose run(coordinator, subId, keyHash, nft, tokenId, treasury)
deploys it and returns its address. we'll run it once from the wallet that holds the NFT and owns
the subscription, so leave the raffle ready to go. we're on foundry with solidity 0.8.30, going to
mainnet.
