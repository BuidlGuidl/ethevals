You are an evaluation judge with access to the filesystem. Explore the codebase in your working directory and evaluate it against the following criteria.

A coding agent built it from a starter project and this request:

    Our users hold USDC and USDT on Ethereum mainnet and want to earn on them without leaving our app, so could you add a Savings page to this project? A connected user should be able to deposit either token into Aave v3, see how much they have deposited including interest so far and the current APY, and withdraw part or all of it at any time. The chain to use is in `chain_context.json`.

What else you have:
- The built page, running at <url>. Use it with the Playwright browser tools.
- A test wallet, already connected. Its address is <address>. It holds 10 ETH, 10,000 USDC and 10,000 USDT, and approves every request the page makes. It mines each withdrawal a day after the page asks for it.
- The chain, a private copy of Ethereum mainnet at <rpc url>. You can read it with `cast`.
- `move-time <days>`, which moves the chain's clock forward.
- `old-usdt-approval`, which leaves a 1 USDT approval from the wallet to Aave's pool.
- `full-cap`, which lowers Aave's USDC supply cap so that only a few thousand USDC more fit.
- `wallet-network <chain id>`, which puts the wallet on another network. The wallet switches back when the page asks, and sends nothing while it is away.

Cover at least these:
- a deposit of 100 USDC
- looking at the page again after `move-time 30`
- a withdrawal of 40 USDC, then withdrawing everything
- a deposit of 100 USDT after `old-usdt-approval`
- a USDC deposit larger than Aave will accept, after `full-cap`
- pressing Deposit while the wallet is on another network

After you finish, our code reads the chain and the wallet's log to check other things. So make sure the deposits and withdrawals above go through, and only read the chain yourself. Every transaction must come from the page.

{criteria}
