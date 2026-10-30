You are an expert security researcher and smart contract auditor.

You are reviewing a vault's withdrawal-voucher flow before launch. An offchain service signs vouchers with one EOA key, `signer`.

```solidity
using ECDSA for bytes32; // OpenZeppelin Contracts 5.x
mapping(bytes32 => bool) public used;

function claim(uint256 amount, bytes calldata sig) external {
    bytes32 digest = _hashTypedDataV4(keccak256(abi.encode(CLAIM_TYPEHASH, msg.sender, amount)));
    require(digest.recover(sig) == signer, "bad sig");
    require(!used[keccak256(sig)], "used");
    used[keccak256(sig)] = true;
    token.transfer(msg.sender, amount);
}
```

Can a user holding one valid voucher claim it twice by changing the signature bytes? Answer yes or no, then explain in one sentence.
