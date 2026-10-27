import { createConfig, http } from 'wagmi'

import { chain, rpcUrl } from './chain.ts'

export const config = createConfig({
  chains: [chain],
  transports: {
    [chain.id]: http(rpcUrl),
  },
})

declare module 'wagmi' {
  interface Register {
    config: typeof config
  }
}
