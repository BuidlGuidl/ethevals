import { randomBytes } from 'node:crypto';
import {
  bytesToHex, createPublicClient, encodeFunctionData, http, parseAbi,
  type Address, type Hex,
} from 'viem';
import { mainnet } from 'viem/chains';

const usdc: Address = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48';
const abi = parseAbi([
  'function deposit(address depositor,uint256 amount,uint256 validAfter,uint256 validBefore,bytes32 nonce,bytes signature)',
]);

export async function prepareDeposit({ contract, depositor, amount }: {
  contract: Address;
  depositor: Address;
  amount: bigint;
}) {
  const rpcUrl = process.env.RPC_URL;
  if (!rpcUrl) throw new Error('Set RPC_URL to the mainnet RPC endpoint.');
  const client = createPublicClient({ chain: mainnet, transport: http(rpcUrl) });
  const block = await client.getBlock();
  const validAfter = 0n;
  const validBefore = block.timestamp + 7n * 24n * 60n * 60n;
  const nonce = bytesToHex(randomBytes(32));
  const typedData = {
    domain: { name: 'USD Coin', version: '2', chainId: 1, verifyingContract: usdc },
    types: {
      ReceiveWithAuthorization: [
        { name: 'from', type: 'address' },
        { name: 'to', type: 'address' },
        { name: 'value', type: 'uint256' },
        { name: 'validAfter', type: 'uint256' },
        { name: 'validBefore', type: 'uint256' },
        { name: 'nonce', type: 'bytes32' },
      ],
    },
    primaryType: 'ReceiveWithAuthorization',
    message: { from: depositor, to: contract, value: amount, validAfter, validBefore, nonce },
  } satisfies Parameters<ReturnType<typeof import('viem/accounts').privateKeyToAccount>['signTypedData']>[0];

  return {
    typedData,
    keeperTx(signature: Hex) {
      return {
        to: contract,
        data: encodeFunctionData({
          abi, functionName: 'deposit', args: [depositor, amount, validAfter, validBefore, nonce, signature],
        }),
      };
    },
  };
}
