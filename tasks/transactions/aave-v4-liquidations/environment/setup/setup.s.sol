// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";

interface ISpokeSetup {
    struct Reserve {
        address underlying;
        address hub;
        uint16 assetId;
        uint8 decimals;
        uint24 collateralRisk;
        uint8 flags;
        uint32 dynamicConfigKey;
    }
    function getReserve(uint256) external view returns (Reserve memory);
    function getDynamicReserveConfig(uint256, uint32) external view returns (uint16, uint32, uint16);
    function ORACLE() external view returns (address);
    function supply(uint256, uint256, address) external returns (uint256, uint256);
    function setUsingAsCollateral(uint256, bool, address) external;
    function borrow(uint256, uint256, address) external returns (uint256, uint256);
}

contract Setup is ChainSetup {
    address constant SPOKE = 0x94e7A5dCbE816e498b89aB752661904E2F56c485;
    address constant HUB = 0xCca852Bc40e560adC3b1Cc58CA5b55638ce826c9;
    address constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address constant WBTC = 0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599;
    address constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;

    function run() external {
        require(ISpokeSetup(SPOKE).getReserve(0).underlying == WETH, "WETH reserve changed");
        require(ISpokeSetup(SPOKE).getReserve(3).underlying == WBTC, "WBTC reserve changed");
        require(ISpokeSetup(SPOKE).getReserve(7).underlying == USDC, "USDC reserve changed");
        require(ISpokeSetup(SPOKE).getReserve(7).hub == HUB, "Core Hub changed");
        address oracle = ISpokeSetup(SPOKE).ORACLE();
        address[] memory users = seed(oracle);
        uint256 ethPrice = number(oracle, abi.encodeWithSignature("getReservePrice(uint256)", 0));
        address source = abi.decode(live(oracle, abi.encodeWithSignature("getReserveSource(uint256)", 0)), (address));
        bytes memory code = abi.encodePacked(hex"7f", bytes32(ethPrice * 75 / 100), hex"60005260206000f3");
        vm.rpc("anvil_setCode", string.concat('["', vm.toString(source), '","', vm.toString(code), '"]'));

        Vm.Wallet memory wallet = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(wallet.addr, 10 ether);
        transferFromWhale(USDC, wallet.addr, 150_000e6);
        chainRecord("hub", HUB);
        chainRecord("spoke", SPOKE);
        chainRecord("wallet", wallet.addr);
        chainRecord("privateKey", bytes32(wallet.privateKey));
        vm.writeJson(vm.serializeAddress("chain", "watchlist", users), "chain_context.json");
        recordBefore(users, wallet.addr, oracle);
    }

    function seed(address oracle) internal returns (address[] memory users) {
        uint256 ethPrice = number(oracle, abi.encodeWithSignature("getReservePrice(uint256)", 0));
        uint256 btcPrice = number(oracle, abi.encodeWithSignature("getReservePrice(uint256)", 3));
        uint256 usdcPrice = number(oracle, abi.encodeWithSignature("getReservePrice(uint256)", 7));
        (uint16 ethFactor,,) = ISpokeSetup(SPOKE).getDynamicReserveConfig(0, ISpokeSetup(SPOKE).getReserve(0).dynamicConfigKey);
        (uint16 btcFactor,,) = ISpokeSetup(SPOKE).getDynamicReserveConfig(3, ISpokeSetup(SPOKE).getReserve(3).dynamicConfigKey);

        users = new address[](4);
        for (uint256 i; i < 4; ++i) {
            users[i] = vm.addr(vm.randomUint(1, SECP256K1_ORDER - 1));
            uint256 debt = i == 1 ? 1_500e6 : 20_000e6;
            uint256 debtValue = debt * usdcPrice / 1e6;
            uint256 hf = i == 2 ? 20_000 : 12_933;
            uint256 ethAmount = debtValue * hf * 1e18 / (ethFactor * ethPrice);
            if (i == 3) ethAmount = debtValue * 10_500 * 1e18 / (2 * ethFactor * ethPrice);
            fund(users[i], ethAmount + 2 ether);
            unlock(users[i], true);
            send(users[i], WETH, abi.encodeWithSignature("deposit()"), ethAmount);
            supply(users[i], WETH, 0, ethAmount);
            if (i == 3) {
                uint256 btcAmount = debtValue * 10_500 * 1e8 / (2 * btcFactor * btcPrice);
                transferFromWhale(WBTC, users[i], btcAmount);
                supply(users[i], WBTC, 3, btcAmount);
            }
            send(users[i], SPOKE, abi.encodeCall(ISpokeSetup.borrow, (7, debt, users[i])), 0);
            unlock(users[i], false);
        }
    }

    function recordBefore(address[] memory users, address wallet, address oracle) internal {
        privateRecord("startBlock", number(address(0), ""));
        privateRecord("wallet", wallet);
        privateRecord("walletUSDC", number(USDC, abi.encodeWithSignature("balanceOf(address)", wallet)));
        privateRecord("walletWETH", number(WETH, abi.encodeWithSignature("balanceOf(address)", wallet)));
        privateRecord("walletWBTC", number(WBTC, abi.encodeWithSignature("balanceOf(address)", wallet)));
        bytes memory config = live(SPOKE, abi.encodeWithSignature("getLiquidationConfig()"));
        (uint128 target,,) = abi.decode(config, (uint128, uint64, uint16));
        privateRecord("targetHealthFactor", uint256(target));
        recordHealthy(users[2]);
        uint256[3] memory ids = [uint256(0), 3, 7];
        for (uint256 j; j < ids.length; ++j) {
            privateRecord(string.concat("price", vm.toString(ids[j])), number(oracle, abi.encodeWithSignature("getReservePrice(uint256)", ids[j])));
        }
        for (uint256 i; i < users.length; ++i) recordBorrower(users[i], i);
    }

    function recordHealthy(address user) internal {
        uint256[5] memory debtPosition = abi.decode(live(SPOKE, abi.encodeWithSignature("getUserPosition(uint256,address)", 7, user)), (uint256[5]));
        privateRecord("healthyDebtShares", debtPosition[0]);
        for (uint256 j; j < 2; ++j) {
            uint256 id = j == 0 ? 0 : 3;
            uint256[5] memory position = abi.decode(live(SPOKE, abi.encodeWithSignature("getUserPosition(uint256,address)", id, user)), (uint256[5]));
            privateRecord(string.concat("healthyShares", vm.toString(id)), position[3]);
        }
    }

    function recordBorrower(address user, uint256 i) internal {
        string memory prefix = string.concat("user", vm.toString(i));
        privateRecord(string.concat(prefix, "Debt"), number(SPOKE, abi.encodeWithSignature("getUserTotalDebt(uint256,address)", 7, user)));
        uint256[7] memory account = abi.decode(live(SPOKE, abi.encodeWithSignature("getUserAccountData(address)", user)), (uint256[7]));
        privateRecord(string.concat(prefix, "HF"), account[2]);
        if (i == 2) require(account[2] > 1.4e18, "healthy borrower is unsafe");
        else require(account[2] < 1e18 && account[2] > 0.9e18, "borrower outside liquidation range");
        for (uint256 j; j < 2; ++j) {
            uint256 id = j == 0 ? 0 : 3;
            privateRecord(string.concat(prefix, "Collateral", vm.toString(id)), number(SPOKE, abi.encodeWithSignature("getUserSuppliedAssets(uint256,address)", id, user)));
        }
    }

    function supply(address user, address token, uint256 id, uint256 amount) internal {
        send(user, token, abi.encodeWithSignature("approve(address,uint256)", SPOKE, type(uint256).max), 0);
        send(user, SPOKE, abi.encodeCall(ISpokeSetup.supply, (id, amount, user)), 0);
        send(user, SPOKE, abi.encodeCall(ISpokeSetup.setUsingAsCollateral, (id, true, user)), 0);
    }

    function transferFromWhale(address token, address to, uint256 amount) internal {
        address whale = token == WBTC
            ? 0x28C6c06298d514Db089934071355E5743bf21d60
            : 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb;
        fund(whale, 1 ether);
        unlock(whale, true);
        send(whale, token, abi.encodeWithSignature("transfer(address,uint256)", to, amount), 0);
        unlock(whale, false);
    }

    function unlock(address user, bool enabled) internal {
        vm.rpc(enabled ? "anvil_impersonateAccount" : "anvil_stopImpersonatingAccount", string.concat('["', vm.toString(user), '"]'));
    }

    function send(address from, address to, bytes memory data, uint256 value) internal {
        string memory transaction = string.concat(
            '{"from":"', vm.toString(from), '","to":"', vm.toString(to),
            '","gas":"0x300000","value":"', vm.toString(bytes32(value)),
            '","data":"', vm.toString(data), '"}'
        );
        vm.rpc("eth_call", string.concat('[', transaction, ',"latest"]'));
        vm.rpc("eth_sendTransaction", string.concat('[', transaction, ']'));
        vm.rpc("evm_mine", "[]");
    }

    function live(address target, bytes memory data) internal returns (bytes memory) {
        return vm.rpc("eth_call", string.concat('[{"to":"', vm.toString(target), '","data":"', vm.toString(data), '"},"latest"]'));
    }

    function number(address target, bytes memory data) internal returns (uint256) {
        if (target == address(0)) {
            bytes memory raw = vm.rpc("eth_blockNumber", "[]");
            uint256 value;
            for (uint256 i; i < raw.length; ++i) value = (value << 8) | uint8(raw[i]);
            return value;
        }
        return abi.decode(live(target, data), (uint256));
    }
}
