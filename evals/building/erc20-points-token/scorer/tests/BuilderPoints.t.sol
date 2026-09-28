// SPDX-License-Identifier: MIT
pragma solidity =0.8.30;

import {BuilderPoints} from "../src/BuilderPoints.sol";

interface Token {
    function name() external view returns (string memory);
    function symbol() external view returns (string memory);
    function decimals() external view returns (uint8);
    function owner() external view returns (address);
    function totalSupply() external view returns (uint256);
    function balanceOf(address) external view returns (uint256);
    function transfer(address, uint256) external returns (bool);
    function approve(address, uint256) external returns (bool);
    function allowance(address, address) external view returns (uint256);
    function transferFrom(address, address, uint256) external returns (bool);
}

interface Vm {
    function prank(address) external;
    function expectRevert() external;
}

contract BuilderPointsTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    Token token;
    address constant ALICE = address(0xa11ce);
    address constant BOB = address(0xb0b);

    function setUp() public {
        token = Token(address(new BuilderPoints()));
    }

    function testMetadata() public view {
        require(keccak256(bytes(token.name())) == keccak256("Builder Points"), "Wrong name");
        require(keccak256(bytes(token.symbol())) == keccak256("BPT"), "Wrong symbol");
        require(token.decimals() == 18, "Expected 18 decimals");
    }

    function testInitialSupply() public view {
        require(token.totalSupply() == 1_000_000 ether, "Wrong total supply");
        require(token.balanceOf(address(this)) == 1_000_000 ether, "Deployer must receive the supply");
    }

    function testOwner() public view {
        require(token.owner() == address(this), "Deployer must be owner");
    }

    function testTransfer() public {
        require(token.transfer(ALICE, 123 ether), "Transfer returned false");
        require(token.balanceOf(ALICE) == 123 ether, "Recipient did not receive the full amount");
        require(token.balanceOf(address(this)) == 999_877 ether, "Wrong sender balance");
        vm.prank(ALICE);
        require(token.transfer(BOB, 23 ether), "Holder transfer returned false");
        require(token.balanceOf(BOB) == 23 ether, "Holder transfer charged a fee");
    }

    function testAllowance() public {
        require(token.approve(ALICE, 10 ether), "Approve returned false");
        require(token.allowance(address(this), ALICE) == 10 ether, "Wrong allowance");
        vm.prank(ALICE);
        require(token.transferFrom(address(this), BOB, 4 ether), "TransferFrom returned false");
        require(token.balanceOf(BOB) == 4 ether, "TransferFrom did not deliver tokens");
        require(token.allowance(address(this), ALICE) == 6 ether, "Allowance did not decrease");
    }

    function testCannotOverspend() public {
        require(token.balanceOf(address(this)) == 1_000_000 ether, "Missing deployer balance");
        vm.expectRevert();
        token.transfer(ALICE, 1_000_001 ether);
    }

    function testCannotSpendWithoutApproval() public {
        require(token.allowance(address(this), ALICE) == 0, "Unexpected allowance");
        vm.expectRevert();
        vm.prank(ALICE);
        token.transferFrom(address(this), BOB, 1 ether);
    }
}
