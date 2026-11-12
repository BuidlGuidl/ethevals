// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Our mint page talks to the collection through this interface.
interface IMintPage {
    /// Mints `count` pieces to the caller.
    function mint(uint256 count) external;

    /// Finishes a piece that still has something outstanding after its mint, so its final art shows.
    /// Anyone may call it. Does nothing to a piece that is already final.
    function reveal(uint256 tokenId) external;
}
