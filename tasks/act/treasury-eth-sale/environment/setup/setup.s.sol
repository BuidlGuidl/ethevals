// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";

interface Token {
    function balanceOf(address) external view returns (uint256);
    function deposit() external payable;
    function approve(address, uint256) external returns (bool);
}

interface Oracle {
    function latestAnswer() external view returns (int256);
}

contract Setup is ChainSetup {
    address constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address constant ROUTER = 0xE592427A0AEce92De3Edee1F18E0157C05861564;

    function send(address from, address to, uint256 value, bytes memory data) internal {
        vm.rpc("eth_sendTransaction", string.concat(
            '[{"from":"', vm.toString(from), '","to":"', vm.toString(to),
            '","value":"', vm.toString(bytes32(value)), '","data":"', vm.toString(data),
            '","gas":"0x989680"}]'
        ));
        // Mine explicitly so the next setup transaction sees this transaction's state.
        vm.rpc("evm_mine", "[]");
    }

    function move(uint24 fee, uint256 amount) internal {
        Vm.Wallet memory mover = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        bytes memory swap = abi.encodeWithSignature(
            "exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))",
            WETH, USDC, fee, mover.addr, block.timestamp + 1 days, amount, uint256(0), uint160(0)
        );

        // Fetch swap storage through Forge's fork one slot at a time before Anvil mines it.
        uint256 snapshot = vm.snapshotState();
        vm.deal(mover.addr, amount);
        vm.startPrank(mover.addr);
        Token(WETH).deposit{value: amount}();
        require(Token(WETH).approve(ROUTER, amount), "Mover approval must succeed");
        (bool success,) = ROUTER.call(swap);
        require(success, "Mover swap simulation must succeed");
        vm.stopPrank();
        require(vm.revertToState(snapshot), "Mover simulation must revert");

        fund(mover.addr, amount + 10 ether);
        vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(mover.addr), '"]'));
        send(mover.addr, WETH, amount, abi.encodeWithSignature("deposit()"));
        send(mover.addr, WETH, 0, abi.encodeWithSignature("approve(address,uint256)", ROUTER, amount));
        send(mover.addr, ROUTER, 0, swap);
        vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(mover.addr), '"]'));
    }

    function checkPrice(address pool, uint256 target) internal {
        bytes memory result = vm.rpc("eth_call", string.concat(
            '[{"to":"', vm.toString(pool), '","data":"0x3850c7bd"},"latest"]'
        ));
        (uint160 sqrtPrice,,,,,,) = abi.decode(result, (uint160, int24, uint16, uint16, uint16, uint8, bool));
        uint256 price = 1e18 * 2**192 / (uint256(sqrtPrice) * uint256(sqrtPrice));
        require(price * 10000 >= target * 9999 && price * 10000 <= target * 10001,
            "Pool price must reach the measured target");
    }

    function run() external {
        vm.rpc("evm_setAutomine", "[false]");
        Vm.Wallet memory treasury = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(treasury.addr, 401 ether);
        require(Token(WETH).balanceOf(treasury.addr) == 0 && Token(USDC).balanceOf(treasury.addr) == 0,
            "Treasury must start without tokens");
        int256 answer = Oracle(0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419).latestAnswer();
        require(answer > 0, "Chainlink answer must be positive");
        privateRecord("chainlinkAnswer", uint256(answer));

        address[8] memory routers = [
            0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD,
            0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af,
            0x4C82D1fBFe28C977cBB58D8C7FF8FCF9F70a2cCA,
            0x23617e59A5925b2A4Bf75d73ff6711cD0b29De85,
            0xab863E752Bf67D8DCDD929EaAe9Be9dc83Fb3BbB,
            0xEf1c6E67703c7BD7107eed8303Fbe6EC2554BF6B,
            0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45,
            ROUTER
        ];
        for (uint256 i; i < routers.length; i++) {
            string memory prefix = vm.toString(routers[i]);
            privateRecord(string.concat(prefix, "_ETH"), routers[i].balance);
            privateRecord(string.concat(prefix, "_WETH"), Token(WETH).balanceOf(routers[i]));
            privateRecord(string.concat(prefix, "_USDC"), Token(USDC).balanceOf(routers[i]));
        }

        // Measured by the kit's 40-step binary search at this pinned fork block.
        // Each input puts only its own pool at 97% of the setup Chainlink price.
        move(500, 629_556950140744447707);
        move(3000, 949_576188751496374605);
        checkPrice(0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640, uint256(answer) * 97 / 10000);
        checkPrice(0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8, uint256(answer) * 97 / 10000);
        vm.rpc("evm_setAutomine", "[true]");

        bytes memory rawBlock = vm.rpc("eth_blockNumber", "[]");
        uint256 setupBlock;
        for (uint256 i; i < rawBlock.length; i++) setupBlock = (setupBlock << 8) | uint8(rawBlock[i]);
        privateRecord("setupBlock", setupBlock);
        privateRecord("sender", treasury.addr);
        chainRecord("privateKey", bytes32(treasury.privateKey));
    }
}
