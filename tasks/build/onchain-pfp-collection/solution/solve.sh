#!/bin/sh
set -eu
mkdir -p /workspace/src /workspace/script
cat > /workspace/src/PFPCollection.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC2981} from "@openzeppelin/contracts/token/common/ERC2981.sol";
import {IERC4906} from "@openzeppelin/contracts/interfaces/IERC4906.sol";
import {IERC165} from "@openzeppelin/contracts/utils/introspection/IERC165.sol";
import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";
import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";
import {IArtUpload} from "./interfaces/IArtUpload.sol";
import {IMintPage} from "./interfaces/IMintPage.sol";

/// A 1,000-piece generative PFP collection whose parts, draw and renderer all live in this contract.
contract PFPCollection is ERC721, ERC2981, IERC4906, IArtUpload, IMintPage {
    uint256 public constant MAX_SUPPLY = 1000;
    uint256 public constant WALLET_LIMIT = 2;
    uint96 public constant ROYALTY_BPS = 500;

    struct Part {
        string name;
        string svg;
    }

    struct Layer {
        string name;
        Part[] parts;
    }

    address public immutable artist;
    Layer[] private _layers;
    bool public mintOpen;
    uint256 public minted;
    mapping(address => uint256) public mintedBy;
    /// The block whose hash draws the piece. It is after the mint, so the minter cannot see the draw.
    mapping(uint256 => uint256) public drawBlock;
    mapping(uint256 => bytes32) private _seed;

    error NotArtist();
    error MintAlreadyOpen();
    error MintNotOpen();
    error NothingToMint();
    error NoLayers();
    error EmptyLayer(uint256 layer);
    error SoldOut();
    error WalletLimitReached();
    error ArtIsFinal();
    error DrawPending();

    constructor(address artist_) ERC721("Onchain PFPs", "PFP") {
        artist = artist_;
        _setDefaultRoyalty(artist_, ROYALTY_BPS);
    }

    modifier onlyArtist() {
        if (msg.sender != artist) revert NotArtist();
        _;
    }

    // ---- the artist's upload tool ----

    function addLayer(string calldata name) external onlyArtist returns (uint256) {
        if (mintOpen) revert MintAlreadyOpen();
        _layers.push();
        _layers[_layers.length - 1].name = name;
        return _layers.length - 1;
    }

    function addPart(uint256 layer, string calldata name, string calldata svg) external onlyArtist returns (uint256) {
        if (mintOpen) revert MintAlreadyOpen();
        Part[] storage parts = _layers[layer].parts;
        parts.push(Part(name, svg));
        return parts.length - 1;
    }

    /// A fix lands on every piece that uses the part, until the last piece is minted.
    function updatePart(uint256 layer, uint256 part, string calldata name, string calldata svg) external onlyArtist {
        if (minted == MAX_SUPPLY) revert ArtIsFinal();
        _layers[layer].parts[part] = Part(name, svg);
        if (minted > 0) emit BatchMetadataUpdate(0, type(uint256).max);
    }

    function openMint() external onlyArtist {
        if (mintOpen) revert MintAlreadyOpen();
        if (_layers.length == 0) revert NoLayers();
        for (uint256 i; i < _layers.length; ++i) {
            if (_layers[i].parts.length == 0) revert EmptyLayer(i);
        }
        mintOpen = true;
    }

    function layerCount() external view returns (uint256) {
        return _layers.length;
    }

    function partCount(uint256 layer) external view returns (uint256) {
        return _layers[layer].parts.length;
    }

    // ---- the mint page ----

    function mint(uint256 count) external {
        if (!mintOpen) revert MintNotOpen();
        if (count == 0) revert NothingToMint();
        uint256 first = minted;
        if (first + count > MAX_SUPPLY) revert SoldOut();
        if (mintedBy[msg.sender] + count > WALLET_LIMIT) revert WalletLimitReached();
        // Effects first: a receiver that re-enters from onERC721Received sees the cap already spent.
        mintedBy[msg.sender] += count;
        minted = first + count;
        for (uint256 i; i < count; ++i) {
            uint256 tokenId = first + i;
            drawBlock[tokenId] = block.number + 1;
            _safeMint(msg.sender, tokenId);
        }
    }

    /// Seals the draw from the hash of the block after the mint. Anyone may call it; the mint page does
    /// when a collector first looks. If nobody did within 256 blocks the hash is gone, so the piece is
    /// drawn from the next block instead and this call must be repeated.
    function reveal(uint256 tokenId) external {
        _requireOwned(tokenId);
        if (_seed[tokenId] != 0) return;
        uint256 target = drawBlock[tokenId];
        if (block.number <= target) revert DrawPending();
        bytes32 hash = blockhash(target);
        if (hash == 0) {
            drawBlock[tokenId] = block.number + 1;
            return;
        }
        _seed[tokenId] = keccak256(abi.encodePacked(hash, tokenId));
        emit MetadataUpdate(tokenId);
    }

    // ---- metadata ----

    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        _requireOwned(tokenId);
        string memory id = Strings.toString(tokenId);
        bytes32 seed = _seed[tokenId];
        if (seed == 0) {
            string memory waiting = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" fill="#222"/>'
                '<text x="12" y="13" font-size="3" text-anchor="middle" fill="#eee">drawing...</text></svg>';
            return _dataJson(string.concat('{"name":"PFP #', id, '","description":"This piece is being drawn. It settles a block after its mint.",'
                '"image":"', _dataSvg(waiting), '"}'));
        }
        string memory body;
        string memory attributes;
        uint256 count = _layers.length;
        for (uint256 i; i < count; ++i) {
            Layer storage layer = _layers[i];
            Part storage part = layer.parts[uint256(keccak256(abi.encodePacked(seed, i))) % layer.parts.length];
            body = string.concat(body, part.svg);
            attributes = string.concat(attributes, i == 0 ? "" : ",", '{"trait_type":"', Strings.escapeJSON(layer.name),
                '","value":"', Strings.escapeJSON(part.name), '"}');
        }
        string memory svg = string.concat('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" shape-rendering="crispEdges">',
            body, "</svg>");
        return _dataJson(string.concat('{"name":"PFP #', id, '","description":"One of 1,000 pieces drawn and rendered onchain.",'
            '"image":"', _dataSvg(svg), '","attributes":[', attributes, "]}"));
    }

    function supportsInterface(bytes4 interfaceId) public view override(ERC721, ERC2981, IERC165) returns (bool) {
        return interfaceId == bytes4(0x49064906) || super.supportsInterface(interfaceId);
    }

    function _dataSvg(string memory svg) private pure returns (string memory) {
        return string.concat("data:image/svg+xml;base64,", Base64.encode(bytes(svg)));
    }

    function _dataJson(string memory json) private pure returns (string memory) {
        return string.concat("data:application/json;base64,", Base64.encode(bytes(json)));
    }
}
SOL
cat > /workspace/script/Deploy.s.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Script} from "forge-std/Script.sol";
import {PFPCollection} from "../src/PFPCollection.sol";

contract Deploy is Script {
    function run(address artist) external returns (address) {
        vm.startBroadcast();
        PFPCollection collection = new PFPCollection(artist);
        vm.stopBroadcast();
        return address(collection);
    }
}
SOL
