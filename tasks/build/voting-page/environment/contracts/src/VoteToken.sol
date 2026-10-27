// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ERC20, IERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Wrapper} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Wrapper.sol";
import {ERC20Votes} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import {ERC20Permit} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import {Nonces} from "@openzeppelin/contracts/utils/Nonces.sol";
import {IVoteToken} from "./interfaces/IVoteToken.sol";

contract VoteToken is ERC20Wrapper, ERC20Votes, ERC20Permit, IVoteToken {
    constructor(IERC20 underlyingToken)
        ERC20("Wrapped TOKEN", "vTOKEN") ERC20Wrapper(underlyingToken) ERC20Permit("Wrapped TOKEN") {}

    function depositFor(address account, uint256 amount) public override(ERC20Wrapper, IVoteToken) returns (bool) {
        return super.depositFor(account, amount);
    }

    function withdrawTo(address account, uint256 amount) public override(ERC20Wrapper, IVoteToken) returns (bool) {
        return super.withdrawTo(account, amount);
    }

    function decimals() public view override(ERC20, ERC20Wrapper) returns (uint8) {
        return super.decimals();
    }

    function _update(address from, address to, uint256 amount) internal override(ERC20, ERC20Votes) {
        super._update(from, to, amount);
    }

    function nonces(address owner) public view override(ERC20Permit, Nonces) returns (uint256) {
        return super.nonces(owner);
    }
}
