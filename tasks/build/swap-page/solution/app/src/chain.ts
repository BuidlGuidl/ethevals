import { getAddress } from 'viem'
import { mainnet } from 'wagmi/chains'

import chainContext from '../chain_context.json'

if (chainContext.chainId !== mainnet.id) {
  throw new Error(
    `chain_context.json chainId ${chainContext.chainId} is not Ethereum mainnet; the Swap page only supports mainnet`,
  )
}

export const chain = mainnet
export const rpcUrl = chainContext.rpcUrl
export const treasury = getAddress(chainContext.treasury)
