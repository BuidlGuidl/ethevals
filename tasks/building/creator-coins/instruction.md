Hello! We're building a creator-coin platform. anyone calls create(name, symbol), which returns a
new coin with a fixed 1B supply that all goes straight into a Uniswap v3 pool against WETH (1% fee
tier), opening at a 10 ETH market cap. nobody, us included, can ever pull that liquidity. trading
fees split 70% to the coin's creator and 30% to us, and the constructor takes the address our share
goes to. anyone can call collect(coin) to pay out a coin's fees, and a creator can change where
their share goes with setPayoutRecipient(coin, recipient). could you put it in src/CreatorCoins.sol
as a contract called CreatorCoins? it's a Foundry project on solidity 0.8.30, for mainnet.
