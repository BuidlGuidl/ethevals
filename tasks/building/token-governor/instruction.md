Hi! Our token TOKEN is live, a plain ERC-20 with a fixed 100M supply, and we can't change it.
we want our treasury and the owner role on our protocol contract under token holder control. a
proposal passes when at least 4% of the supply votes for it, with more for than against, then waits
two days before anyone can execute it. our delegates vote through snapshot, so it has to be a
standard governor, and our frontend's wrap flow talks to the vote token through
src/interfaces/IVoteToken.sol. put the governor in src/TokenGovernor.sol as TokenGovernor, and a
deploy script in script/Deploy.s.sol whose run(token) returns the governor address and the address
we should move the protocol's ownership and the treasury to. we're on foundry with solidity 0.8.30.
