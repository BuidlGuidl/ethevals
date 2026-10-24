import { createPublicClient, http, type Address, type Hex } from 'viem';
import { mainnet } from 'viem/chains';

const client = createPublicClient({ chain: mainnet, transport: http(process.env.RPC_URL) });
const types = {
  Vote: [
    { name: 'proposalId', type: 'uint256' },
    { name: 'voter', type: 'address' },
    { name: 'support', type: 'uint8' },
  ],
} as const;

export function voteToSign(message: { proposalId: bigint; voter: Address; support: 0 | 1 | 2 }) {
  return {
    domain: { name: 'Holder votes', version: '1', chainId: 1 },
    types,
    primaryType: 'Vote',
    message,
  } as const;
}

export async function checkVote(typedData: ReturnType<typeof voteToSign>, signature: Hex): Promise<boolean> {
  try {
    return await client.verifyTypedData({ ...typedData, address: typedData.message.voter, signature });
  } catch {
    return false;
  }
}
