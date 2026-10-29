// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// The artist's upload tool talks to the collection through this interface.
interface IArtUpload {
    /// Adds a layer. Layers draw bottom to top in the order added. Returns the layer's index.
    function addLayer(string calldata name) external returns (uint256);

    /// Adds a part to a layer: the trait's name and the SVG fragment that draws it.
    /// Returns the part's index in its layer.
    function addPart(uint256 layer, string calldata name, string calldata svg) external returns (uint256);

    /// Replaces a part's name and SVG fragment.
    function updatePart(uint256 layer, uint256 part, string calldata name, string calldata svg) external;

    /// Opens the public mint once every part is in.
    function openMint() external;

    function layerCount() external view returns (uint256);

    function partCount(uint256 layer) external view returns (uint256);
}
