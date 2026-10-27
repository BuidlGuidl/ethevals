import { createRequire } from 'node:module';
import path from 'node:path';

export const require = createRequire(path.join(process.env.VERIFIER_DEPS || '/root/savings-verifier', 'package.json'));
export const { chromium } = require('playwright');
export const {
  createWalletClient, defineChain, http, encodeFunctionData, decodeFunctionData,
  parseAbi, toHex, formatUnits, hashTypedData,
  createPublicClient, decodeFunctionResult, getAddress, zeroAddress, parseAbiParameters,
  decodeAbiParameters, decodeEventLog, toFunctionSelector, keccak256, encodeAbiParameters,
  toEventSelector, pad, parseUnits,
} = require('viem');
export const { generatePrivateKey, privateKeyToAccount } = require('viem/accounts');
