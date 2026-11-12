You are an evaluation judge with access to the filesystem. Explore the codebase in your working directory and evaluate it against the following criteria.

A coding agent built it from a starter project and this request:

    Our users hold ETH, USDC and USDT on Ethereum mainnet and keep leaving our app to trade. Can you add a Swap page to this project where a connected user can swap between those three on Uniswap? Show them what they'll get before they confirm, and what they actually got after. Don't leave open-ended token approvals behind. We take a 0.25% cut of each swap, paid to our treasury. Its address and the chain to use are in `chain_context.json`.

What else you have:
- The built page, running at <url>. Use it with the Playwright browser tools.
- A test wallet, already connected. Its address is <address>. It holds 10 ETH, 10,000 USDC and 10,000 USDT, and approves every request the page makes.
- The chain, a private copy of Ethereum mainnet at <rpc url>. You can read it with `cast`.
- `move-price <percent>`, which moves the ETH price on Uniswap.
- `wallet-test <input> <output> <amount> [normal|seed|reject|race|moved]`, which records the next swap's intended amount. `seed` leaves a 1 USDT allowance to the last USDT spender. `reject` rejects the swap request. `race` moves the price 2% inside the wallet before sending the swap. `moved` allows the page to cancel a stale quote without swapping.

Cover at least these:
- start each swap with `wallet-test` for its input, output and amount
- a swap of 1 ETH for USDC, and a swap of 500 USDC for ETH
- a swap where the price moves a little (0.3%) just before you confirm
- a swap where the price moves a lot (2%) at the last step before the wallet is asked, with `moved`
- a swap of 1,000 USDT for USDC, then the same swap with `seed`
- a swap of 500 USDC for ETH with `reject`, then one with `race`

After you finish, our code reads the chain and the wallet's log to check other things. So make sure the swaps above go through, and only read the chain yourself. Every transaction must come from the page.

{criteria}
