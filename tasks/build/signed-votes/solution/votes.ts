import { createPublicClient, hashTypedData, http, parseAbi, type Address, type Hex } from 'viem';
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

export async function checkVote(fields: Parameters<typeof voteToSign>[0], signature: Hex): Promise<boolean> {
  try {
    const typedData = voteToSign(fields);
    if (signature === '0x') {
      return await client.readContract({
        address: fields.voter,
        abi: parseAbi(['function isValidSignature(bytes32 hash,bytes signature) view returns (bytes4)']),
        functionName: 'isValidSignature',
        args: [hashTypedData(typedData), signature],
      }) === '0x1626ba7e';
    }
    return await client.verifyTypedData({ ...typedData, address: fields.voter, signature });
  } catch {
    return false;
  }
}
