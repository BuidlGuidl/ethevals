// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

interface ISpoke {
    struct Reserve {
        address underlying;
        address hub;
        uint16 assetId;
        uint8 decimals;
        uint24 collateralRisk;
        uint8 flags;
        uint32 dynamicConfigKey;
    }
    struct Position {
        uint120 drawnShares;
        uint120 premiumShares;
        int200 premiumOffsetRay;
        uint120 suppliedShares;
        uint32 dynamicConfigKey;
    }
    function ORACLE() external view returns (address);
    function getReserve(uint256) external view returns (Reserve memory);
    function getReserveCount() external view returns (uint256);
    function getUserPosition(uint256, address) external view returns (Position memory);
    function getUserTotalDebt(uint256, address) external view returns (uint256);
    function getUserSuppliedAssets(uint256, address) external view returns (uint256);
    function getUserAccountData(address) external view returns (uint256, uint256, uint256, uint256, uint256, uint256, uint256);
    function getLiquidationConfig() external view returns (uint128, uint64, uint16);
}

interface IOracle {
    function getReservePrice(uint256) external view returns (uint256);
}

contract LiquidationsCheck is Test {
    using stdJson for string;

    struct Liquidation {
        address borrower;
        uint256 collateral;
        uint256 debt;
        uint256 reserveId;
    }
    struct Report {
        address borrower;
        uint256 collateralHuman;
        uint256 collateralRaw;
        uint256 debtHuman;
        uint256 debtRaw;
        uint256 reserveId;
    }

    ISpoke spoke;
    IOracle oracle;
    address wallet;
    address[] users;
    string beforeState;
    Liquidation[] events;

    function setUp() public {
        string memory context = vm.readFile("chain_context.json");
        beforeState = vm.readFile("private_chain_context.json");
        spoke = ISpoke(context.readAddress(".spoke"));
        wallet = context.readAddress(".wallet");
        users = context.readAddressArray(".watchlist");
        vm.createSelectFork("chain");
        oracle = IOracle(spoke.ORACLE());
        if (beforeState.readUint(".eventCount") > 0) {
            Liquidation[] memory recorded = abi.decode(beforeState.parseRaw(".events"), (Liquidation[]));
            for (uint256 i; i < recorded.length; ++i) events.push(recorded[i]);
        }
    }

    function test_underwaterPositionsBroughtToTarget() public view {
        (uint128 target,,) = spoke.getLiquidationConfig();
        for (uint256 i; i < users.length; ++i) {
            if (i == 2) continue;
            if (spoke.getUserTotalDebt(7, users[i]) == 0) continue;
            (,, uint256 hf,,,,) = spoke.getUserAccountData(users[i]);
            assertGe(hf + 1e14, target, "underwater borrower did not reach the Spoke target");
        }
    }

    function test_smallPositionClearedWhole() public view {
        assertEq(spoke.getUserTotalDebt(7, users[1]), 0, "small borrower still has USDC debt");
    }

    function test_healthyPositionUntouched() public view {
        uint256 debtBefore = beforeState.readUint(".user2Debt");
        assertApproxEqAbs(spoke.getUserTotalDebt(7, users[2]), debtBefore, debtBefore / 10_000 + 2, "healthy borrower debt changed beyond interest");
        assertEq(spoke.getUserPosition(7, users[2]).drawnShares, beforeState.readUint(".healthyDebtShares"), "healthy borrower debt shares changed");
        uint256[2] memory ids = [uint256(0), 3];
        for (uint256 j; j < ids.length; ++j) {
            string memory key = string.concat(".user2Collateral", vm.toString(ids[j]));
            uint256 collateralBefore = beforeState.readUint(key);
            assertApproxEqAbs(spoke.getUserSuppliedAssets(ids[j], users[2]), collateralBefore, collateralBefore / 10_000 + 2, "healthy borrower collateral changed beyond interest");
            assertEq(spoke.getUserPosition(ids[j], users[2]).suppliedShares, beforeState.readUint(string.concat(".healthyShares", vm.toString(ids[j]))), "healthy borrower collateral shares changed");
        }
    }

    function test_keeperCameOutAhead() public view {
        uint256 repaid;
        for (uint256 i; i < users.length; ++i) {
            uint256 debtBefore = beforeState.readUint(string.concat(".user", vm.toString(i), "Debt"));
            uint256 debtAfter = spoke.getUserTotalDebt(7, users[i]);
            if (debtBefore > debtAfter) repaid += debtBefore - debtAfter;
        }
        assertGt(repaid, 0, "keeper repaid no watched debt");
        uint256 eventDebt;
        uint256 collateralValue;
        for (uint256 i; i < events.length; ++i) {
            eventDebt += events[i].debt;
            collateralValue += value(events[i].reserveId, events[i].collateral);
        }
        assertGt(eventDebt, 0, "chain has no watched liquidations");
        uint256 debtValue = value(7, eventDebt);
        assertGt(collateralValue, debtValue, "liquidations paid no bonus");
        uint256 minimumGain = (collateralValue - debtValue) * repaid / eventDebt / 4;
        uint256 beforeWorth = value(7, beforeState.readUint(".walletUSDC"))
            + value(0, beforeState.readUint(".walletWETH"))
            + value(3, beforeState.readUint(".walletWBTC"));
        uint256 afterAssets;
        uint256 afterDebt;
        for (uint256 id; id < spoke.getReserveCount(); ++id) {
            ISpoke.Reserve memory reserve = spoke.getReserve(id);
            uint256 assets = spoke.getUserSuppliedAssets(id, wallet);
            if (id == 0 || id == 3 || id == 7) assets += IERC20(reserve.underlying).balanceOf(wallet);
            afterAssets += value(id, assets);
            afterDebt += value(id, spoke.getUserTotalDebt(id, wallet));
        }
        assertGe(afterAssets, beforeWorth + minimumGain + afterDebt, "keeper retained less than a quarter of the bonus");
    }

    function test_reportMatchesChain() public view {
        assertTrue(beforeState.readBool(".reportValid"), "liquidations.json is missing or has invalid liquidation entries");
        assertGt(events.length, 0, "chain has no liquidations to report");
        assertEq(beforeState.readUint(".reportCount"), events.length, "report does not have one entry per liquidation");
        Report[] memory reports = abi.decode(beforeState.parseRaw(".reports"), (Report[]));
        bool[] memory used = new bool[](reports.length);
        for (uint256 i; i < events.length; ++i) {
            bool matched;
            for (uint256 j; j < reports.length; ++j) {
                if (used[j] || reports[j].borrower != events[i].borrower || reports[j].reserveId != events[i].reserveId) continue;
                bool debtMatches = close(reports[j].debtHuman, events[i].debt) || close(reports[j].debtRaw, events[i].debt);
                bool collateralMatches = close(reports[j].collateralHuman, events[i].collateral) || close(reports[j].collateralRaw, events[i].collateral);
                if (!debtMatches || !collateralMatches) continue;
                used[j] = true;
                matched = true;
                break;
            }
            assertTrue(matched, "report borrower or amounts do not match a chain liquidation within 1%");
        }
    }

    function value(uint256 id, uint256 amount) internal view returns (uint256) {
        return amount * oracle.getReservePrice(id) / 10 ** spoke.getReserve(id).decimals;
    }

    function close(uint256 reported, uint256 actual) internal pure returns (bool) {
        uint256 delta = reported > actual ? reported - actual : actual - reported;
        return delta <= actual / 100 + 1;
    }
}
