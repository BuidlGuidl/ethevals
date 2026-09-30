// SPDX-License-Identifier: MIT
pragma solidity =0.8.30;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

contract BuilderPoints is ERC20, Ownable {
    constructor() ERC20("Builder Points", "BPT") Ownable(msg.sender) {
        _mint(msg.sender, 1_000_000 * 10 ** decimals());
    }
}
