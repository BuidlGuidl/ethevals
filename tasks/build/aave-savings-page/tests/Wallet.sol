// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// Installed only in the verifier's fork to model an atomic-capable wallet.
contract Wallet {
    struct Call {
        address to;
        uint256 value;
        bytes data;
    }

    function isValidSignature(bytes32 digest, bytes calldata signature) external view returns (bytes4) {
        if (signature.length != 65) return 0xffffffff;
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }
        if (v < 27) v += 27;
        return ecrecover(digest, v, r, s) == address(this) ? bytes4(0x1626ba7e) : bytes4(0xffffffff);
    }

    function execute(Call[] calldata calls) external payable {
        require(msg.sender == address(this), "Only the account can execute calls");
        for (uint256 i; i < calls.length; ++i) {
            (bool ok, bytes memory result) = calls[i].to.call{value: calls[i].value}(calls[i].data);
            if (!ok) assembly { revert(add(result, 32), mload(result)) }
        }
    }
}
