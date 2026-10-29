// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Bridge {
    function build(address recipient, uint256 amount) external pure returns (bytes memory payload) {
        payload = abi.encodePacked(uint8(1), recipient, amount); // flag, recipient, amount
        delete payload[0];                                      // clear the flag
    }
}

library Decode {
    function recipient(bytes memory p) internal pure returns (address r) { assembly { r := shr(96, mload(add(p, 33))) } }
    function amount(bytes memory p) internal pure returns (uint256 a) { assembly { a := mload(add(p, 53)) } }
}

contract Proof {
    function testDeleteZeroesRecipient() public {
        bytes memory p = new Bridge().build(address(0xA11CE), 5 ether);
        require(p.length == 53 && uint8(p[0]) == 0, "shape");
        require(Decode.recipient(p) == address(0), "recipient survived");
        require(Decode.amount(p) == 5 ether, "amount changed");
    }
}
