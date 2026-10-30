// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IAavePool} from "../../src/interfaces/IAavePool.sol";
import {MockERC20} from "./MockERC20.sol";

/// @notice An Aave v3 stand-in for one reserve. aToken balances are scaled by a liquidity index that
///         grows when interest is paid; the reserve's cash sits in the aToken contract.
contract MockAavePool {
    uint256 internal constant RAY = 1e27;

    MockERC20 public immutable underlying;
    MockAToken public immutable aToken;
    uint256 public liquidityIndex = RAY;
    uint256 public configuration = 1 << 56;

    constructor(MockERC20 underlying_) {
        underlying = underlying_;
        aToken = new MockAToken(this, address(underlying_));
    }

    function getConfiguration(address) external view returns (IAavePool.ReserveConfigurationMap memory) {
        return IAavePool.ReserveConfigurationMap(configuration);
    }

    function supply(address, uint256 amount, address onBehalfOf, uint16) external {
        require(configuration & (1 << 57) == 0 && configuration & (1 << 60) == 0, "unavailable");
        underlying.transferFrom(msg.sender, address(aToken), amount);
        aToken.mintScaled(onBehalfOf, amount * RAY / liquidityIndex);
    }

    function withdraw(address, uint256 amount, address to) external returns (uint256) {
        require(configuration & (1 << 60) == 0, "paused");
        if (amount == type(uint256).max) amount = aToken.balanceOf(msg.sender);
        require(amount <= underlying.balanceOf(address(aToken)), "liquidity");
        uint256 scaled = (amount * RAY + liquidityIndex - 1) / liquidityIndex;
        uint256 held = aToken.scaledBalanceOf(msg.sender);
        if (scaled > held) scaled = held;
        aToken.burnScaled(msg.sender, scaled, to, amount);
        return amount;
    }

    /// @notice Borrowers pay `assets` of interest into the reserve.
    function accrueInterest(uint256 assets) external {
        liquidityIndex += assets * RAY / aToken.scaledTotalSupply();
        underlying.mint(address(aToken), assets);
    }

    /// @notice Borrowers take `assets` of the reserve's cash.
    function borrow(uint256 assets) external {
        aToken.sendUnderlying(msg.sender, assets);
    }

    function setConfiguration(uint256 configuration_) external {
        configuration = configuration_;
    }
}

contract MockAToken {
    uint256 internal constant RAY = 1e27;

    MockAavePool public immutable POOL;
    address public immutable UNDERLYING_ASSET_ADDRESS;
    mapping(address => uint256) public scaledBalanceOf;
    uint256 public scaledTotalSupply;

    constructor(MockAavePool pool, address underlying) {
        POOL = pool;
        UNDERLYING_ASSET_ADDRESS = underlying;
    }

    modifier onlyPool() {
        require(msg.sender == address(POOL), "pool");
        _;
    }

    function balanceOf(address account) external view returns (uint256) {
        return scaledBalanceOf[account] * POOL.liquidityIndex() / RAY;
    }

    function mintScaled(address to, uint256 scaled) external onlyPool {
        scaledBalanceOf[to] += scaled;
        scaledTotalSupply += scaled;
    }

    function burnScaled(address from, uint256 scaled, address to, uint256 amount) external onlyPool {
        scaledBalanceOf[from] -= scaled;
        scaledTotalSupply -= scaled;
        POOL.underlying().transfer(to, amount);
    }

    function sendUnderlying(address to, uint256 amount) external onlyPool {
        POOL.underlying().transfer(to, amount);
    }
}
