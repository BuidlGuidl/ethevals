// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IERC20} from "../interfaces/IERC20.sol";

/// @notice Token transfers that accept tokens returning no value and revert on a false return.
library SafeTransfer {
    error TransferFailed(address token);

    function safeTransfer(IERC20 token, address to, uint256 amount) internal {
        _call(token, abi.encodeCall(IERC20.transfer, (to, amount)));
    }

    function safeTransferFrom(IERC20 token, address from, address to, uint256 amount) internal {
        _call(token, abi.encodeCall(IERC20.transferFrom, (from, to, amount)));
    }

    function _call(IERC20 token, bytes memory data) private {
        (bool success, bytes memory returned) = address(token).call(data);
        if (!success || (returned.length != 0 && !abi.decode(returned, (bool))) || address(token).code.length == 0) {
            revert TransferFailed(address(token));
        }
    }
}
