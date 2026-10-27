import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(path.join(process.env.VERIFIER_DEPS || '/root/savings-verifier', 'package.json'));
export const { chromium } = require('playwright');
export const {
  createWalletClient, defineChain, http, encodeFunctionData, decodeFunctionData,
  parseAbi, toHex, formatUnits, hashTypedData,
} = require('viem');
export const { generatePrivateKey, privateKeyToAccount } = require('viem/accounts');
