// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test, Vm} from "forge-std/Test.sol";
import {IArtUpload} from "../workspace/src/interfaces/IArtUpload.sol";
import {IMintPage} from "../workspace/src/interfaces/IMintPage.sol";
import {Deploy} from "../workspace/script/Deploy.s.sol";

interface ICollection is IArtUpload, IMintPage {
    function name() external view returns (string memory);
    function symbol() external view returns (string memory);
    function tokenURI(uint256 tokenId) external view returns (string memory);
    function ownerOf(uint256 tokenId) external view returns (address);
    function balanceOf(address owner) external view returns (uint256);
    function supportsInterface(bytes4 interfaceId) external view returns (bool);
    function royaltyInfo(uint256 tokenId, uint256 salePrice) external view returns (address, uint256);
}

/// Plain Solidity helpers, so the picker contract can use them without cheatcodes.
library Codec {
    function startsWith(string memory text, string memory prefix) internal pure returns (bool) {
        bytes memory value = bytes(text);
        bytes memory head = bytes(prefix);
        if (value.length < head.length) return false;
        for (uint256 i; i < head.length; ++i) if (value[i] != head[i]) return false;
        return true;
    }

    function contains(string memory text, string memory needle) internal pure returns (bool) {
        bytes memory haystack = bytes(text);
        bytes memory key = bytes(needle);
        if (key.length == 0 || haystack.length < key.length) return key.length == 0;
        for (uint256 i; i + key.length <= haystack.length; ++i) {
            if (haystack[i] != key[0]) continue;
            bool same = true;
            for (uint256 j = 1; j < key.length; ++j) {
                if (haystack[i + j] != key[j]) {
                    same = false;
                    break;
                }
            }
            if (same) return true;
        }
        return false;
    }

    function slice(string memory text, uint256 start, uint256 end) internal pure returns (string memory) {
        bytes memory value = bytes(text);
        bytes memory out = new bytes(end - start);
        for (uint256 i = start; i < end; ++i) out[i - start] = value[i];
        return string(out);
    }

    /// The payload of a data URI with the given media type, decoded from base64 when it says so.
    /// Returns ok = false when the URI is not such a data URI.
    function dataPayload(string memory uri, string memory mediaType) internal pure returns (string memory payload, bool ok) {
        string memory prefix = string.concat("data:", mediaType);
        if (!startsWith(uri, prefix)) return ("", false);
        bytes memory value = bytes(uri);
        uint256 comma = bytes(prefix).length;
        while (comma < value.length && value[comma] != ",") ++comma;
        if (comma >= value.length) return ("", false);
        string memory parameters = slice(uri, bytes(prefix).length, comma);
        string memory rest = slice(uri, comma + 1, value.length);
        if (contains(parameters, "base64")) return (string(base64Decode(rest)), true);
        return (rest, true);
    }

    function base64Decode(string memory input) internal pure returns (bytes memory out) {
        bytes memory data = bytes(input);
        uint256 length = data.length;
        while (length > 0 && data[length - 1] == "=") --length;
        out = new bytes((length * 3) / 4);
        uint256 written;
        uint256 buffer;
        uint256 bits;
        for (uint256 i; i < length; ++i) {
            buffer = (buffer << 6) | sextet(data[i]);
            bits += 6;
            if (bits >= 8) {
                bits -= 8;
                out[written++] = bytes1(uint8(buffer >> bits));
                buffer &= (1 << bits) - 1;
            }
        }
    }

    function sextet(bytes1 character) private pure returns (uint256) {
        uint8 value = uint8(character);
        if (value >= 0x41 && value <= 0x5a) return value - 0x41;
        if (value >= 0x61 && value <= 0x7a) return value - 0x61 + 26;
        if (value >= 0x30 && value <= 0x39) return value - 0x30 + 52;
        if (value == 0x2b || value == 0x2d) return 62;
        if (value == 0x2f || value == 0x5f) return 63;
        revert("not base64");
    }
}

contract Forwarder {
    function forward(address target, bytes calldata data) external returns (bytes memory) {
        (bool ok, bytes memory ret) = target.call(data);
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }
        return ret;
    }
}

/// A contract wallet such as a Safe: its owner sends the transaction, the wallet makes the call.
contract ContractWallet {
    address public immutable owner;

    constructor(address owner_) {
        owner = owner_;
    }

    function exec(address target, bytes calldata data) external {
        require(msg.sender == owner, "not the owner");
        (bool ok, bytes memory ret) = target.call(data);
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }
    }

    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return this.onERC721Received.selector;
    }
}

/// The code an EOA delegates to under EIP-7702: it runs at the EOA's own address.
contract Delegate7702 {
    function execute(address target, bytes calldata data) external payable {
        require(msg.sender == address(this), "only the account itself");
        (bool ok, bytes memory ret) = target.call{value: msg.value}(data);
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }
    }

    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return this.onERC721Received.selector;
    }

    receive() external payable {}
}

/// Mints two and tries to mint again from inside onERC721Received.
contract Reenterer {
    IMintPage immutable page;
    bool entered;

    constructor(address collection) {
        page = IMintPage(collection);
    }

    function go() external {
        page.mint(2);
    }

    function onERC721Received(address, address, uint256, bytes calldata) external returns (bytes4) {
        if (!entered) {
            entered = true;
            try page.mint(2) {} catch {}
            try page.mint(1) {} catch {}
        }
        return this.onERC721Received.selector;
    }
}

/// Mints one piece and keeps it only if the draw it can read in the same transaction is the rare one.
contract Picker {
    using Codec for string;

    ICollection immutable collection;
    string rare;
    uint256 hookId;
    bool sawHook;

    constructor(address collection_, string memory rare_) {
        collection = ICollection(collection_);
        rare = rare_;
    }

    function onERC721Received(address, address, uint256 tokenId, bytes calldata) external returns (bytes4) {
        hookId = tokenId;
        sawHook = true;
        return this.onERC721Received.selector;
    }

    function attempt(uint256 expectedId) external {
        collection.mint(1);
        uint256 tokenId = sawHook ? hookId : expectedId;
        require(collection.ownerOf(tokenId) == address(this), "picker cannot find its piece");
        (string memory json, bool ok) = collection.tokenURI(tokenId).dataPayload("application/json");
        require(ok && json.contains(string.concat('"', rare, '"')), "not the draw the picker wanted");
    }
}

/// Owns a piece and, long after every block hash window, reveals it only if the draw it can read
/// in the same transaction is the rare one.
contract LateRevealer {
    using Codec for string;

    ICollection immutable collection;
    string rare;

    constructor(address collection_, string memory rare_) {
        collection = ICollection(collection_);
        rare = rare_;
    }

    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return this.onERC721Received.selector;
    }

    function attempt(uint256 tokenId) external {
        collection.reveal(tokenId);
        (string memory json, bool ok) = collection.tokenURI(tokenId).dataPayload("application/json");
        require(ok && json.contains(string.concat('"', rare, '"')), "not the draw the revealer wanted");
    }
}

contract PFPCollectionTest is Test {
    using Codec for string;

    address constant ARTIST = address(0xA7715);
    address constant STRANGER = address(0x57A9E);
    uint256 constant SUPPLY = 1000;
    uint256 constant CALL_GAS_CAP = 50_000_000;
    bytes32 constant TRANSFER = keccak256("Transfer(address,address,uint256)");
    bytes32 constant METADATA_UPDATE = keccak256("MetadataUpdate(uint256)");
    bytes32 constant BATCH_METADATA_UPDATE = keccak256("BatchMetadataUpdate(uint256,uint256)");
    uint256 constant BACKGROUND = 0;
    uint256 constant BODY = 1;
    uint256 constant HAT = 4;
    string constant RARE = "Golden";

    struct Piece {
        string json;
        string name;
        string svg;
        string[] traitTypes;
        string[] values;
    }

    string[] layerNames;
    string[][] partNames;
    string[][] partSvgs;
    uint256[] layerIds;
    uint256[][] partIds;

    Deploy deployer;
    address deployerAccount;
    ICollection collection;
    uint256 nextWallet = 0x100000;
    mapping(uint256 => mapping(bytes32 => bool)) seen;
    uint256[] distinct;

    function setUp() public {
        vm.warp(1_800_000_000);
        vm.roll(1_000_000);
        loadArt();
    }

    // ---- the artist's parts ----

    function layer(string memory name) internal {
        layerNames.push(name);
        partNames.push();
        partSvgs.push();
        distinct.push(0);
    }

    function part(string memory name, string memory svg) internal {
        partNames[partNames.length - 1].push(name);
        partSvgs[partSvgs.length - 1].push(svg);
    }

    function fill(string memory shape, string memory color) internal pure returns (string memory) {
        return string.concat(shape, ' fill="#', color, '"/>');
    }

    function loadArt() internal {
        layer("Background");
        string memory bg = '<rect width="24" height="24"';
        part("Sky", fill(bg, "8ecae6"));
        part("Sand", fill(bg, "f4d35e"));
        part("Mint", fill(bg, "b7e4c7"));
        part("Rose", fill(bg, "f7a1c4"));
        part("Slate", fill(bg, "6c757d"));
        part("Plum", fill(bg, "7b2cbf"));
        part("Ink", fill(bg, "1b263b"));
        part(RARE, fill(bg, "ffb703"));
        layer("Body");
        string memory body = '<rect x="6" y="13" width="12" height="11"';
        part("Round", fill(body, "a0522d"));
        part("Slim", fill(body, "2a9d8f"));
        part("Boxy", fill(body, "e76f51"));
        part("Fluffy", fill(body, "ffffff"));
        part("Robot", fill(body, "adb5bd"));
        layer("Head");
        string memory head = '<rect x="7" y="4" width="10" height="9"';
        part("Bear", fill(head, "8b5a2b"));
        part("Cat", fill(head, "f4a261"));
        part("Frog", fill(head, "52b788"));
        part("Owl", fill(head, "b08968"));
        part("Fox", fill(head, "e85d04"));
        part("Ghost", fill(head, "f8f9fa"));
        layer("Eyes");
        string memory eyes = '<rect x="9" y="7" width="2" height="2"';
        part("Dot", fill(eyes, "000000"));
        part("Wide", fill(eyes, "212529"));
        part("Sleepy", fill(eyes, "495057"));
        part("Laser", fill(eyes, "d00000"));
        layer("Hat");
        string memory hat = '<rect x="6" y="2" width="12" height="3"';
        part("Top Hat", fill(hat, "000000"));
        part('"Fancy" Fedora', fill(hat, "6f4e37"));
        part("Back\\slash Beanie", fill(hat, "c1121f"));
        part(unicode"Béret", fill(hat, "003049"));
        part('Cap / "Visor"', fill(hat, "0077b6"));
        part("Halo", fill(hat, "ffd60a"));
    }

    function hostileName(string memory name) internal pure returns (bool) {
        return name.contains('"') || name.contains("\\");
    }

    // ---- deploying, uploading, minting ----

    // Each check deploys from inside its own test function, so the script runs as the account
    // `forge script` would broadcast from. setUp does not get that sender.
    function deploy() internal {
        deployer = new Deploy();
        vm.startBroadcast();
        (, address sender,) = vm.readCallers();
        vm.stopBroadcast();
        deployerAccount = sender;
        vm.etch(sender, type(Forwarder).runtimeCode);
        bytes memory result = Forwarder(sender).forward(address(deployer), abi.encodeCall(deployer.run, (ARTIST)));
        vm.etch(sender, "");
        collection = ICollection(abi.decode(result, (address)));
        assertTrue(address(collection).code.length > 0, "run(artist) did not return a deployed contract");
    }

    function upload() internal {
        vm.startPrank(ARTIST, ARTIST);
        for (uint256 i; i < layerNames.length; ++i) {
            layerIds.push(collection.addLayer(layerNames[i]));
            partIds.push();
            for (uint256 j; j < partNames[i].length; ++j) {
                partIds[i].push(collection.addPart(layerIds[i], partNames[i][j], partSvgs[i][j]));
            }
            assertEq(collection.partCount(layerIds[i]), partNames[i].length, "partCount does not count the uploaded parts");
        }
        assertEq(collection.layerCount(), layerNames.length, "layerCount does not count the uploaded layers");
        collection.openMint();
        vm.stopPrank();
    }

    function setupCollection() internal {
        deploy();
        upload();
    }

    function freshWallet() internal returns (address) {
        return address(uint160(nextWallet++));
    }

    function nextBlock() internal {
        vm.roll(block.number + 1);
        vm.warp(block.timestamp + 12);
        vm.prevrandao(keccak256(abi.encode("prevrandao", block.number)));
    }

    function mintAs(address who, uint256 count) internal returns (uint256[] memory ids) {
        vm.recordLogs();
        vm.prank(who, who);
        collection.mint(count);
        ids = mintedIds(who, count);
    }

    /// The ids `who` just received, from the Transfer events recorded since `vm.recordLogs()`.
    function mintedIds(address who, uint256 count) internal returns (uint256[] memory ids) {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        ids = new uint256[](count);
        uint256 found;
        for (uint256 i; i < logs.length; ++i) {
            Vm.Log memory log = logs[i];
            if (log.emitter != address(collection) || log.topics.length != 4 || log.topics[0] != TRANSFER) continue;
            if (log.topics[1] != bytes32(0) || log.topics[2] != bytes32(uint256(uint160(who)))) continue;
            assertLt(found, count, "mint emitted more Transfer events than pieces");
            ids[found++] = uint256(log.topics[3]);
        }
        assertEq(found, count, "mint did not emit one Transfer from the zero address per piece");
        for (uint256 i; i < count; ++i) assertEq(collection.ownerOf(ids[i]), who, "minter does not own the piece");
    }

    /// Mints `count` pieces two per wallet, moving the chain along every few wallets.
    function mintMany(uint256 count) internal returns (uint256[] memory ids) {
        ids = new uint256[](count);
        for (uint256 i; i < count;) {
            if (i % 20 == 0) nextBlock();
            uint256 batch = count - i >= 2 ? 2 : 1;
            uint256[] memory minted = mintAs(freshWallet(), batch);
            for (uint256 j; j < batch; ++j) ids[i + j] = minted[j];
            i += batch;
        }
    }

    function append(uint256[] memory a, uint256[] memory b) internal pure returns (uint256[] memory out) {
        out = new uint256[](a.length + b.length);
        for (uint256 i; i < a.length; ++i) out[i] = a[i];
        for (uint256 i; i < b.length; ++i) out[a.length + i] = b[i];
    }

    /// Two blocks after the last mint, a stranger finishes every piece that still needs it.
    function settle(uint256[] memory ids) internal {
        nextBlock();
        nextBlock();
        for (uint256 i; i < ids.length; ++i) {
            vm.prank(STRANGER, STRANGER);
            try collection.reveal(ids[i]) {} catch {}
        }
    }

    // ---- reading pieces ----

    function stringAt(string memory json, string memory key) internal view returns (string memory value, bool ok) {
        if (!vm.keyExistsJson(json, key)) return ("", false);
        try vm.parseJsonString(json, key) returns (string memory parsed) {
            return (parsed, true);
        } catch {
            return ("", false);
        }
    }

    /// Reads a piece the way a marketplace would. `problem` is empty when the metadata is well formed.
    function read(uint256 tokenId) internal view returns (Piece memory piece, string memory problem) {
        string memory label = string.concat("piece ", vm.toString(tokenId));
        (bool ok, bytes memory ret) = address(collection).staticcall(abi.encodeCall(collection.tokenURI, (tokenId)));
        if (!ok) return (piece, string.concat(label, ": tokenURI reverts"));
        string memory uri = abi.decode(ret, (string));
        (piece.json, ok) = uri.dataPayload("application/json");
        if (!ok) return (piece, string.concat(label, ": tokenURI is not a data:application/json URI"));
        try vm.parseJson(piece.json) {} catch {
            return (piece, string.concat(label, ": the metadata is not valid JSON"));
        }
        (piece.name, ok) = stringAt(piece.json, ".name");
        if (!ok || bytes(piece.name).length == 0) return (piece, string.concat(label, ": the metadata has no name"));
        (string memory image, bool hasImage) = stringAt(piece.json, ".image");
        if (hasImage) {
            (piece.svg, ok) = image.dataPayload("image/svg+xml");
            if (!ok) return (piece, string.concat(label, ": image is not a data:image/svg+xml URI"));
        } else {
            (piece.svg, ok) = stringAt(piece.json, ".image_data");
            if (!ok) return (piece, string.concat(label, ": the metadata has no image"));
        }
        if (!piece.svg.contains("<svg")) return (piece, string.concat(label, ": the image is not an SVG"));
        uint256 count;
        while (vm.keyExistsJson(piece.json, string.concat(".attributes[", vm.toString(count), "]"))) ++count;
        piece.traitTypes = new string[](count);
        piece.values = new string[](count);
        for (uint256 i; i < count; ++i) {
            string memory key = string.concat(".attributes[", vm.toString(i), "]");
            (piece.traitTypes[i],) = stringAt(piece.json, string.concat(key, ".trait_type"));
            (piece.values[i], ok) = stringAt(piece.json, string.concat(key, ".value"));
            if (!ok) return (piece, string.concat(label, ": attribute ", vm.toString(i), " has no string value"));
        }
    }

    function same(string memory a, string memory b) internal pure returns (bool) {
        return keccak256(bytes(a)) == keccak256(bytes(b));
    }

    /// The index of the piece's part in `layerIndex`, or a problem.
    function partOf(uint256 tokenId, Piece memory piece, uint256 layerIndex) internal view returns (uint256 index, string memory problem) {
        string memory label = string.concat("piece ", vm.toString(tokenId));
        string memory layerName = layerNames[layerIndex];
        uint256 hits;
        string memory value;
        for (uint256 i; i < piece.traitTypes.length; ++i) {
            if (same(piece.traitTypes[i], layerName)) {
                ++hits;
                value = piece.values[i];
            }
        }
        if (hits == 0) return (0, string.concat(label, ": no attribute for the ", layerName, " layer"));
        if (hits > 1) return (0, string.concat(label, ": the ", layerName, " layer appears ", vm.toString(hits), " times"));
        for (uint256 j; j < partNames[layerIndex].length; ++j) {
            if (same(value, partNames[layerIndex][j])) return (j, "");
        }
        return (0, string.concat(label, ": its ", layerName, " is '", value, "', which is not a name the artist gave"));
    }

    /// Checks every layer's attribute against the artist's parts and the SVG against the chosen fragments.
    function checkPiece(uint256 tokenId, Piece memory piece) internal view returns (uint256[] memory chosen, string memory problem) {
        chosen = new uint256[](layerNames.length);
        for (uint256 l; l < layerNames.length; ++l) {
            (chosen[l], problem) = partOf(tokenId, piece, l);
            if (bytes(problem).length != 0) return (chosen, problem);
            if (vm.indexOf(piece.svg, partSvgs[l][chosen[l]]) == type(uint256).max) {
                return (chosen, string.concat("piece ", vm.toString(tokenId), ": the image lacks the SVG of its ", layerNames[l], " part"));
            }
        }
    }

    function fingerprint(Piece memory piece) internal pure returns (bytes32) {
        return keccak256(abi.encode(piece.svg, piece.traitTypes, piece.values));
    }

    function tokenUriGas(uint256 tokenId) internal view returns (uint256) {
        uint256 before = gasleft();
        collection.tokenURI(tokenId);
        return before - gasleft();
    }

    function covered(Vm.Log[] memory logs, uint256 tokenId) internal view returns (bool) {
        for (uint256 i; i < logs.length; ++i) {
            if (logs[i].emitter != address(collection) || logs[i].topics.length == 0) continue;
            if (logs[i].topics[0] == METADATA_UPDATE && logs[i].data.length >= 32) {
                if (abi.decode(logs[i].data, (uint256)) == tokenId) return true;
            } else if (logs[i].topics[0] == BATCH_METADATA_UPDATE && logs[i].data.length >= 64) {
                (uint256 from, uint256 to) = abi.decode(logs[i].data, (uint256, uint256));
                if (from <= tokenId && tokenId <= to) return true;
            }
        }
        return false;
    }

    // ---- the checks ----

    function test_openSeaCanReadIt() public {
        setupCollection();
        assertTrue(bytes(collection.name()).length > 0, "the collection has no name");
        assertTrue(bytes(collection.symbol()).length > 0, "the collection has no symbol");
        address a = freshWallet();
        address b = freshWallet();
        uint256[] memory ids = append(mintAs(a, 2), mintAs(b, 1));
        assertEq(collection.balanceOf(a), 2, "balanceOf does not count the minted pieces");
        bytes4[4] memory interfaces = [bytes4(0x01ffc9a7), bytes4(0x80ac58cd), bytes4(0x5b5e139f), bytes4(0x2a55205a)];
        string[4] memory names = ["ERC-165", "ERC-721", "ERC-721 metadata", "ERC-2981"];
        for (uint256 i; i < interfaces.length; ++i) {
            assertTrue(collection.supportsInterface(interfaces[i]), string.concat("supportsInterface denies ", names[i]));
        }
        assertFalse(collection.supportsInterface(0xffffffff), "supportsInterface accepts 0xffffffff");
        settle(ids);
        uint256 highest;
        for (uint256 i; i < ids.length; ++i) {
            (address receiver, uint256 amount) = collection.royaltyInfo(ids[i], 10 ether);
            assertEq(receiver, ARTIST, "the royalty does not go to the artist");
            assertEq(amount, 0.5 ether, "the royalty is not 5% of the sale price");
            (, amount) = collection.royaltyInfo(ids[i], 10_000);
            assertEq(amount, 500, "the royalty is not 5% of a 10,000 sale");
            (Piece memory piece, string memory problem) = read(ids[i]);
            assertTrue(bytes(problem).length == 0, problem);
            assertGt(piece.traitTypes.length, 0, "the metadata lists no attributes");
            if (ids[i] > highest) highest = ids[i];
        }
        uint256[2] memory unminted = [highest + 1, uint256(1) << 200];
        for (uint256 i; i < unminted.length; ++i) {
            (bool ok,) = address(collection).staticcall(abi.encodeCall(collection.tokenURI, (unminted[i])));
            assertFalse(ok, "tokenURI answers for a piece that was never minted");
            (ok,) = address(collection).staticcall(abi.encodeCall(collection.ownerOf, (unminted[i])));
            assertFalse(ok, "ownerOf answers for a piece that was never minted");
        }
    }

    function test_everyPieceIsItsParts() public {
        setupCollection();
        uint256[] memory ids = mintMany(SUPPLY);
        address late = freshWallet();
        vm.prank(late, late);
        (bool ok,) = address(collection).call(abi.encodeCall(collection.mint, (1)));
        assertFalse(ok, "a 1,001st piece was minted");
        settle(ids);
        for (uint256 i; i < 20; ++i) {
            uint256 used = tokenUriGas(ids[i * 50]);
            assertLt(used, CALL_GAS_CAP, string.concat("piece ", vm.toString(ids[i * 50]), ": tokenURI needs more gas than a node gives one eth_call"));
        }
        bytes32[] memory prints = new bytes32[](SUPPLY);
        vm.pauseGasMetering();
        for (uint256 i; i < SUPPLY; ++i) {
            (Piece memory piece, string memory problem) = read(ids[i]);
            assertTrue(bytes(problem).length == 0, problem);
            (uint256[] memory chosen, string memory mismatch) = checkPiece(ids[i], piece);
            assertTrue(bytes(mismatch).length == 0, mismatch);
            for (uint256 l; l < chosen.length; ++l) {
                bytes32 key = bytes32(chosen[l]);
                if (!seen[l][key]) {
                    seen[l][key] = true;
                    ++distinct[l];
                }
            }
            prints[i] = fingerprint(piece);
        }
        vm.resumeGasMetering();
        for (uint256 l; l < layerNames.length; ++l) {
            assertGt(distinct[l], 1, string.concat("every piece has the same ", layerNames[l]));
        }
        vm.roll(block.number + 300);
        vm.warp(block.timestamp + 3600);
        vm.pauseGasMetering();
        for (uint256 i; i < SUPPLY; i += 7) {
            uint256 index = i + 7 >= SUPPLY ? SUPPLY - 1 : i;
            (Piece memory piece, string memory problem) = read(ids[index]);
            assertTrue(bytes(problem).length == 0, string.concat(problem, " 300 blocks later"));
            assertEq(fingerprint(piece), prints[index], string.concat("piece ", vm.toString(ids[index]), " changed 300 blocks after it settled"));
        }
        vm.resumeGasMetering();
    }

    function test_artistNamesSurviveJson() public {
        setupCollection();
        uint256[] memory ids = mintMany(300);
        settle(ids);
        uint256 hostile;
        vm.pauseGasMetering();
        for (uint256 i; i < ids.length; ++i) {
            (Piece memory piece, string memory problem) = read(ids[i]);
            assertTrue(bytes(problem).length == 0, problem);
            (uint256 hat, string memory mismatch) = partOf(ids[i], piece, HAT);
            assertTrue(bytes(mismatch).length == 0, mismatch);
            assertTrue(vm.indexOf(piece.svg, partSvgs[HAT][hat]) != type(uint256).max,
                string.concat("piece ", vm.toString(ids[i]), ": the image lacks the SVG of its Hat part"));
            if (hostileName(partNames[HAT][hat])) ++hostile;
        }
        vm.resumeGasMetering();
        assertGt(hostile, 0, "no piece drew a hat whose name has a quote or backslash, so nothing was exercised");
    }

    function test_nobodyPicksTheirTraits() public {
        setupCollection();
        uint256 attempts = 150;
        uint256 kept;
        bool sequential = true;
        bool haveLast;
        uint256 lastId;
        for (uint256 i; i < attempts; ++i) {
            nextBlock();
            uint256[] memory ids = mintAs(freshWallet(), 1);
            if (haveLast && ids[0] != lastId + 1) sequential = false;
            lastId = ids[0];
            haveLast = true;
            Picker picker = new Picker(address(collection), RARE);
            uint256 expected = sequential ? lastId + 1 : type(uint256).max;
            try picker.attempt(expected) {
                ++kept;
                if (sequential) lastId = expected;
            } catch {}
        }
        assertEq(kept, 0, string.concat("a contract minter kept ", vm.toString(kept), " of ", vm.toString(attempts),
            " pieces by reverting on draws it did not like"));

        nextBlock();
        uint256[] memory sample = mintMany(6);
        uint256 mintBlock = block.number;
        vm.roll(mintBlock + 2);
        vm.warp(block.timestamp + 24);
        uint256 snapshot = vm.snapshotState();
        bytes32[] memory early = settleAndFingerprint(sample, "two blocks after the mint");
        assertTrue(vm.revertToState(snapshot), "test setup: snapshot did not revert");
        vm.roll(mintBlock + 7);
        vm.warp(block.timestamp + 84);
        vm.prevrandao(keccak256("another reveal block"));
        bytes32[] memory later = settleAndFingerprint(sample, "seven blocks after the mint");
        for (uint256 i; i < sample.length; ++i) {
            assertEq(early[i], later[i], string.concat("piece ", vm.toString(sample[i]),
                ": the draw depends on when the piece is revealed, so a revealer can retry until it likes the result"));
        }
    }

    function settleAndFingerprint(uint256[] memory ids, string memory when) internal returns (bytes32[] memory prints) {
        for (uint256 i; i < ids.length; ++i) {
            vm.prank(STRANGER, STRANGER);
            try collection.reveal(ids[i]) {} catch {}
        }
        prints = new bytes32[](ids.length);
        for (uint256 i; i < ids.length; ++i) {
            (Piece memory piece, string memory problem) = read(ids[i]);
            assertTrue(bytes(problem).length == 0, string.concat(problem, ", read ", when));
            (, string memory mismatch) = checkPiece(ids[i], piece);
            assertTrue(bytes(mismatch).length == 0, string.concat(mismatch, ", read ", when, " and a public reveal"));
            prints[i] = fingerprint(piece);
        }
    }

    function test_lonePieceStillFinishes() public {
        setupCollection();
        nextBlock();
        uint256 lone = mintAs(freshWallet(), 1)[0];
        uint256 attempts = 150;
        LateRevealer[] memory revealers = new LateRevealer[](attempts);
        uint256[] memory held = new uint256[](attempts);
        for (uint256 i; i < attempts; ++i) {
            revealers[i] = new LateRevealer(address(collection), RARE);
            vm.recordLogs();
            vm.prank(address(revealers[i]), address(revealers[i]));
            (bool minted,) = address(collection).call(abi.encodeCall(collection.mint, (1)));
            assertTrue(minted, "a contract could not mint, so no late revealer holds a piece");
            held[i] = mintedIds(address(revealers[i]), 1)[0];
        }

        // Nobody touches the collection until BLOCKHASH (256 blocks) and EIP-2935 (8,191 blocks) have both forgotten the mint.
        vm.roll(block.number + 10_001);
        vm.warp(block.timestamp + 10_001 * 12);
        vm.prevrandao(keccak256("long after the mint"));

        uint256 kept;
        for (uint256 i; i < attempts; ++i) {
            try revealers[i].attempt(held[i]) {
                ++kept;
            } catch {}
        }
        assertEq(kept, 0, string.concat("a contract revealer kept ", vm.toString(kept), " of ", vm.toString(attempts),
            " pieces by revealing late only when the draw it could read in its own transaction was Golden"));

        vm.prank(STRANGER, STRANGER);
        (bool ok,) = address(collection).call(abi.encodeCall(collection.reveal, (lone)));
        assertTrue(ok, string.concat("piece ", vm.toString(lone), ": a stranger's reveal reverted after 10,001 blocks in which nobody revealed it"));
        uint256[] memory single = new uint256[](1);
        single[0] = lone;
        Piece memory piece = finishLate(single)[0];
        bytes32 print = fingerprint(piece);

        vm.roll(block.number + 300);
        vm.warp(block.timestamp + 3600);
        string memory problem;
        (piece, problem) = read(lone);
        assertTrue(bytes(problem).length == 0, string.concat(problem, " 300 blocks after its late reveal"));
        assertEq(fingerprint(piece), print, string.concat("piece ", vm.toString(lone), " changed 300 blocks after its late reveal"));

        vm.prank(STRANGER, STRANGER);
        (ok,) = address(collection).call(abi.encodeCall(collection.reveal, (lone)));
        assertTrue(ok, string.concat("piece ", vm.toString(lone), ": a second reveal of a finished piece reverted"));
        (piece, problem) = read(lone);
        assertTrue(bytes(problem).length == 0, string.concat(problem, " after a second reveal"));
        assertEq(fingerprint(piece), print, string.concat("piece ", vm.toString(lone), " changed on a second reveal"));

        finishLate(held);
    }

    /// A stranger calls reveal on every piece, moves two blocks on and reads, up to three times,
    /// until each piece shows one attribute per layer and each chosen fragment.
    function finishLate(uint256[] memory ids) internal returns (Piece[] memory pieces) {
        pieces = new Piece[](ids.length);
        string memory problem;
        for (uint256 round; round < 3; ++round) {
            for (uint256 i; i < ids.length; ++i) {
                vm.prank(STRANGER, STRANGER);
                try collection.reveal(ids[i]) {} catch {}
            }
            nextBlock();
            nextBlock();
            bool done = true;
            vm.pauseGasMetering();
            for (uint256 i; i < ids.length; ++i) {
                (pieces[i], problem) = read(ids[i]);
                if (bytes(problem).length == 0) (, problem) = checkPiece(ids[i], pieces[i]);
                if (bytes(problem).length != 0) {
                    done = false;
                    break;
                }
            }
            vm.resumeGasMetering();
            if (done) return pieces;
        }
        assertTrue(false, string.concat(problem, ", after 10,001 blocks without a reveal and three rounds of public reveals"));
    }

    function test_fixesReachMarketplaces() public {
        deploy();
        vm.prank(STRANGER, STRANGER);
        vm.expectRevert();
        collection.addLayer("Stranger");
        vm.prank(STRANGER, STRANGER);
        vm.expectRevert();
        collection.openMint();
        upload();
        vm.prank(STRANGER, STRANGER);
        vm.expectRevert();
        collection.updatePart(layerIds[BODY], partIds[BODY][0], "Stranger", "<g/>");

        uint256[] memory ids = mintMany(300);
        bytes32[] memory before = new bytes32[](ids.length);
        bool[] memory readable = new bool[](ids.length);
        for (uint256 i; i < ids.length; ++i) {
            (bool ok, bytes memory ret) = address(collection).staticcall(abi.encodeCall(collection.tokenURI, (ids[i])));
            readable[i] = ok;
            before[i] = keccak256(ret);
        }
        nextBlock();
        nextBlock();
        vm.recordLogs();
        for (uint256 i; i < ids.length; ++i) {
            vm.prank(STRANGER, STRANGER);
            try collection.reveal(ids[i]) {} catch {}
        }
        Vm.Log[] memory revealLogs = vm.getRecordedLogs();
        for (uint256 i; i < ids.length; ++i) {
            (bool ok, bytes memory ret) = address(collection).staticcall(abi.encodeCall(collection.tokenURI, (ids[i])));
            assertTrue(ok, string.concat("piece ", vm.toString(ids[i]), ": tokenURI reverts after a public reveal"));
            if (readable[i] && keccak256(ret) != before[i]) {
                assertTrue(covered(revealLogs, ids[i]), string.concat("piece ", vm.toString(ids[i]),
                    " changed on reveal and no MetadataUpdate or BatchMetadataUpdate covered it"));
            }
        }

        uint256[] memory affected = new uint256[](ids.length);
        uint256 count;
        vm.pauseGasMetering();
        for (uint256 i; i < ids.length; ++i) {
            (Piece memory piece, string memory problem) = read(ids[i]);
            assertTrue(bytes(problem).length == 0, problem);
            (uint256 body, string memory mismatch) = partOf(ids[i], piece, BODY);
            assertTrue(bytes(mismatch).length == 0, mismatch);
            if (body == 0) affected[count++] = ids[i];
        }
        vm.resumeGasMetering();
        assertGt(count, 0, "no piece drew the part the artist fixes, so nothing was exercised");
        string memory fixedName = "Round Belly";
        string memory fixedSvg = fill('<rect x="5" y="13" width="14" height="11"', "cd853f");
        vm.recordLogs();
        vm.prank(ARTIST, ARTIST);
        collection.updatePart(layerIds[BODY], partIds[BODY][0], fixedName, fixedSvg);
        Vm.Log[] memory fixLogs = vm.getRecordedLogs();
        assertTrue(collection.supportsInterface(0x49064906), "supportsInterface denies ERC-4906");
        partNames[BODY][0] = fixedName;
        partSvgs[BODY][0] = fixedSvg;
        vm.pauseGasMetering();
        for (uint256 i; i < count; ++i) {
            (Piece memory piece, string memory problem) = read(affected[i]);
            assertTrue(bytes(problem).length == 0, problem);
            (uint256 body, string memory mismatch) = partOf(affected[i], piece, BODY);
            assertTrue(bytes(mismatch).length == 0 && body == 0, string.concat("piece ", vm.toString(affected[i]), " still shows the old name after the artist's fix"));
            assertTrue(vm.indexOf(piece.svg, fixedSvg) != type(uint256).max, string.concat("piece ", vm.toString(affected[i]), " still draws the old part after the artist's fix"));
            assertTrue(covered(fixLogs, affected[i]), string.concat("the fix to piece ", vm.toString(affected[i]),
                " was not announced with MetadataUpdate or BatchMetadataUpdate"));
        }
        vm.resumeGasMetering();

        uint256[] memory rest = mintMany(SUPPLY - ids.length);
        settle(rest);
        (Piece memory last, string memory lastProblem) = read(rest[rest.length - 1]);
        assertTrue(bytes(lastProblem).length == 0, string.concat(lastProblem, " after mint-out"));
        bytes32 lastPrint = fingerprint(last);
        address[2] memory insiders = [ARTIST, deployerAccount];
        for (uint256 i; i < insiders.length; ++i) {
            vm.prank(insiders[i], insiders[i]);
            vm.expectRevert();
            collection.updatePart(layerIds[BODY], partIds[BODY][1], "Late", "<g/>");
            vm.prank(insiders[i], insiders[i]);
            vm.expectRevert();
            collection.addPart(layerIds[BODY], "Late", "<g/>");
            vm.prank(insiders[i], insiders[i]);
            vm.expectRevert();
            collection.addLayer("Late");
        }
        (last,) = read(rest[rest.length - 1]);
        assertEq(fingerprint(last), lastPrint, "the art changed after mint-out");
    }

    function test_realWalletsCanMint() public {
        setupCollection();
        address eoa = freshWallet();
        mintAs(eoa, 2);
        vm.prank(eoa, eoa);
        (bool ok,) = address(collection).call(abi.encodeCall(collection.mint, (1)));
        assertFalse(ok, "a wallet minted a third piece");
        address greedy = freshWallet();
        vm.prank(greedy, greedy);
        (ok,) = address(collection).call(abi.encodeCall(collection.mint, (3)));
        assertLe(collection.balanceOf(greedy), 2, "mint(3) gave one wallet three pieces");

        address owner = freshWallet();
        ContractWallet safe = new ContractWallet(owner);
        vm.prank(owner, owner);
        (ok,) = address(safe).call(abi.encodeCall(safe.exec, (address(collection), abi.encodeCall(collection.mint, (1)))));
        assertTrue(ok, "a contract wallet such as a Safe could not mint");
        assertEq(collection.balanceOf(address(safe)), 1, "the contract wallet does not own its piece");

        uint256 key = 0xA11CE;
        address delegated = vm.addr(key);
        Delegate7702 implementation = new Delegate7702();
        vm.signAndAttachDelegation(address(implementation), key);
        vm.prank(delegated, delegated);
        (ok,) = address(collection).call(abi.encodeCall(collection.mint, (1)));
        assertEq(delegated.code.length, 23, "test setup: the EIP-7702 delegation is not in place");
        assertTrue(ok, "a wallet with EIP-7702 code could not mint directly");
        vm.prank(delegated, delegated);
        (ok,) = delegated.call(abi.encodeCall(Delegate7702.execute, (address(collection), abi.encodeCall(collection.mint, (1)))));
        assertTrue(ok, "a wallet with EIP-7702 code could not mint from its own batch");
        assertEq(collection.balanceOf(delegated), 2, "the EIP-7702 wallet does not own its two pieces");
    }

    function test_capHoldsAgainstReentry() public {
        setupCollection();
        Reenterer reenterer = new Reenterer(address(collection));
        (bool ok,) = address(reenterer).call(abi.encodeCall(reenterer.go, ()));
        uint256 owned = collection.balanceOf(address(reenterer));
        assertLe(owned, 2, string.concat("a receiver re-entering from onERC721Received minted ", vm.toString(owned), " pieces against a cap of two"));
        if (ok) assertEq(owned, 2, "the honest part of the re-entering mint did not land");
    }
}
