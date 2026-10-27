// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface IUSDC {
    function receiveWithAuthorization(
        address from, address to, uint256 value, uint256 validAfter,
        uint256 validBefore, bytes32 nonce, bytes calldata signature
    ) external;
    function approve(address spender, uint256 value) external returns (bool);
}

interface IVault {
    function deposit(uint256 assets, address receiver) external returns (uint256 shares);
}

contract KeeperDeposits {
    IUSDC constant USDC = IUSDC(0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48);
    IVault constant VAULT = IVault(0xBc65ad17c5C0a2A4D159fa5a503f4992c7B545FE);

    function deposit(
        address depositor, uint256 amount, uint256 validAfter,
        uint256 validBefore, bytes32 nonce, bytes calldata signature
    ) external {
        USDC.receiveWithAuthorization(depositor, address(this), amount, validAfter, validBefore, nonce, signature);
        require(USDC.approve(address(VAULT), amount), "USDC approval failed");
        VAULT.deposit(amount, depositor);
    }
}
