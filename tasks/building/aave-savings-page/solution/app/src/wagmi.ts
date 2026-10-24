import { createConfig, http } from 'wagmi'
import { mainnet } from 'wagmi/chains'

import chainContext from '../chain_context.json'

// The Savings page targets Aave v3 on Ethereum mainnet; chain_context.json
// supplies the RPC endpoint to use for it.
if (chainContext.chainId !== mainnet.id) {
  throw new Error(
    `chain_context.json chainId ${chainContext.chainId} is not Ethereum mainnet (${mainnet.id})`,
  )
}

export const config = createConfig({
  chains: [mainnet],
  transports: {
    [mainnet.id]: http(chainContext.rpcUrl),
  },
})

declare module 'wagmi' {
  interface Register {
    config: typeof config
  }
}
