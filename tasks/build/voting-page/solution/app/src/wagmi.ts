import { createConfig, http } from 'wagmi'
import { defineChain } from 'viem'
import { mainnet, sepolia } from 'wagmi/chains'
import context from '../chain_context.json'

export const tokenChain = defineChain({ id: context.chainId, name: 'TOKEN Chain',
  nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
  rpcUrls: { default: { http: [context.rpcUrl] } } })

export const config = createConfig({
  storage: null,
  chains: [tokenChain, mainnet, sepolia],
  transports: { [tokenChain.id]: http(context.rpcUrl), [mainnet.id]: http(), [sepolia.id]: http() },
})

declare module 'wagmi' {
  interface Register { config: typeof config }
}
