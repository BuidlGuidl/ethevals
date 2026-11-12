# Onchain PFP collection

A three-person studio wants a 1,000-piece generative PFP collection that lives entirely onchain: the artist uploads SVG parts and names, each piece draws its traits at mint, the contract renders the image, a fix can land until the last piece is minted, then the art is final, and it has to show up right on OpenSea.
Hidden Forge tests read every piece the way a marketplace would, try to pick traits with a reverting contract minter, fix a part after mints began, and mint from the wallets people use today.

## The instruction

> We're a three-person studio launching a 1,000-piece generative PFP collection, and we want it fully
> onchain. our artist drew the parts as SVG fragments in a few layers and named every trait herself. her
> upload script already talks to the contract through src/interfaces/IArtUpload.sol: she loads the layers
> and parts from her wallet and opens the mint when she's done. each piece gets its traits from a random
> draw when it's minted and the contract builds the SVG from the stored parts. rarity matters to our
> collectors, so nobody should be able to pick their traits, and it has to run by itself, no oracles or
> outside services. free public mint, two per wallet, and our mint page talks to it through
> src/interfaces/IMintPage.sol. she can still fix a part until the last piece is minted; after that the art
> is final for good, for us too. 5% royalty on secondary sales goes to her. it must show up right on
> OpenSea, images, traits and royalty. put the collection in src/PFPCollection.sol as PFPCollection and a
> deploy script in script/Deploy.s.sol whose run(artist) returns the collection address. we're on foundry
> with solidity 0.8.30, OpenZeppelin 5.7.0 is in lib/.

## What it touches

The instruction leaves out six things a senior developer handles anyway. Each has source code, an incident, or an audit finding behind it.

- **Her names go into JSON.** Nouns' `NFTDescriptorV2` concatenates names into the metadata raw, which is safe only because its names are fixed. The artist's are not: a quote or a backslash in a trait name makes the JSON unparseable, and marketplaces show nothing. Sablier's lockup NFT had this in 2024, a CodeHawks medium. OpenZeppelin's `Strings.escapeJSON`, tightened in 5.6.0, and Solady's `LibString.escapeJSON` exist for it.

- **A draw nobody can see coming.** Nouns seeds from `blockhash(block.number - 1)` and the id; Art Blocks' basic randomizer mixes the previous block hash, the block number and the timestamp. Anything a contract can compute in the mint transaction, a minter contract can compute too, and revert unless the draw is rare. Nouns lives with it because it sells one piece a day at auction. A public mint of 1,000 cannot. The seed has to come from a block after the mint, be sealed from that block whenever it is read, and get settled by anyone, the mint page or a stranger, including for the last piece, before `BLOCKHASH` forgets the hash 256 blocks later.

  | Design | What a reverting minter sees in its own transaction | What a revealer who retries sees |
  | --- | --- | --- |
  | seed from the previous block | the final art, so it keeps only rare draws | nothing to retry |
  | seed from the next block, read at reveal time with the current hash | nothing yet | a new draw every block |
  | seed from the next block, sealed from that block's hash | nothing yet | the same draw every time |

- **Telling marketplaces about a change.** OpenSea caches metadata. A fix to a part, or a reveal that replaces a placeholder, needs `MetadataUpdate` or `BatchMetadataUpdate` from the token contract, and `BatchMetadataUpdate(0, type(uint256).max)` is the refresh-everything convention. ERC-4906 also asks `supportsInterface` to answer for `0x49064906`.

- **A freeze that covers what she can touch.** Nouns' `lockParts` guards parts and palettes but not `setRenderer`, `setBaseURI` or `toggleDataURIEnabled`. Here the test can only reach the upload interface, so it checks that the artist and the deployer lose every mutator at mint-out and that the art stays put.

- **The wallets people mint from.** Since Pectra an EOA may carry 23 bytes of EIP-7702 code, so a `code.length == 0` filter turns away MetaMask smart-account users, and a `tx.origin` filter turns away Safes while no longer stopping batches. OpenZeppelin removed `Address.isContract` in 5.0 for this kind of misuse. `_safeMint` hands control to the receiver, so the per-wallet cap must be spent before it, which is what HypeBears got wrong in 2022.

- **The standard surface.** ERC-721 says `tokenURI` throws for an id that is not a valid NFT. ERC-2981 requires `supportsInterface(0x2a55205a)`. geth and reth cap an `eth_call` at 50M gas by default, so a `tokenURI` above that never reaches an indexer.

## The checks

The agent starts with the two interfaces in `src/interfaces/`, a `foundry.toml` on Solidity 0.8.30 and the Prague EVM, and OpenZeppelin 5.7.0 in `lib/`.
The verifier runs the agent's deploy script the way `forge script` would, uploads five layers and 29 parts as the artist through `IArtUpload`, opens the mint, and drives the collection through `IMintPage` and the ERC-721 views in [`PFPCollection.t.sol`](tests/PFPCollection.t.sol).
It learns token ids from `Transfer` events, decodes the base64 JSON, parses it with Forge's JSON cheatcodes and compares each attribute with the uploaded parts and each image with the chosen SVG fragments.
Each test is one idea, and the reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contracts compile together | all |
| `test_openSeaCanReadIt` | Name and symbol; ERC-165, ERC-721, ERC-721 metadata and ERC-2981 interface ids; 5% royalty to the artist at two prices; a base64 JSON data URI with a name, an SVG image and attributes; `tokenURI` and `ownerOf` revert for ids never minted | marketplace surface |
| `test_everyPieceIsItsParts` | All 1,000 pieces carry one attribute per layer naming an uploaded part and an SVG with each chosen fragment; traits vary; no 1,001st mint; `tokenURI` fits a 50M-gas call; the same art 300 blocks later | rendering |
| `test_artistNamesSurviveJson` | 300 pieces parse as JSON and each Hat value is exactly one of her names, among them `"Fancy" Fedora` and `Back\slash Beanie` | names in JSON |
| `test_nobodyPicksTheirTraits` | 150 fresh contract minters that revert unless the draw they can read in their own transaction is Golden keep nothing; revealing two or seven blocks after the mint gives the same art | the draw |
| `test_lonePieceStillFinishes` | A piece minted and left alone for 10,001 blocks, past BLOCKHASH's 256 and EIP-2935's 8,191, is finished by a stranger's `reveal` that does not revert, carries one attribute per layer and each chosen fragment, is the same 300 blocks later, and a second reveal changes nothing; 150 contract holders that reveal late only when the draw they can read in their own transaction is Golden keep nothing | the window |
| `test_fixesReachMarketplaces` | Strangers cannot upload or open the mint; a fix after 300 mints changes the affected pieces and is announced with ERC-4906 events, as is any reveal that changes a readable piece; after mint-out neither the artist nor the deployer can change a part, and the art stays put | fixes and the freeze |
| `test_realWalletsCanMint` | An EOA mints two and no third; `mint(3)` gives nobody three; a Safe-like contract wallet mints; an EIP-7702 wallet mints directly and from its own batch | wallets |
| `test_capHoldsAgainstReentry` | A receiver that re-enters `mint` from `onERC721Received` ends with at most two pieces | the cap |

A score of 0 says the agent carried some of the ideas but not all. The per-check record says which.

`test_lonePieceStillFinishes` was added after round 1: Opus and Codex both passed 8 of 8 without it, and regraded against the full set Opus passes 9 of 9 while Codex fails that one check by design, since its `reveal` reverts with `EntropyExpired` once the hash is gone.

## Why it matters

Names break metadata where nobody tests.
[Sablier's CodeHawks finding](https://codehawks.cyfrin.io/c/2024-05-Sablier/s/348) shows a token symbol with a double quote breaking the NFT's JSON; the fix is to escape.
[Nouns' descriptor library](https://github.com/nounsDAO/nouns-monorepo/blob/master/packages/nouns-contracts/contracts/libs/NFTDescriptorV2.sol) concatenates raw, and OpenZeppelin's [5.6.0 changelog](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/CHANGELOG.md) shows `escapeJSON` still being tightened in 2026.

Same-block seeds are the norm in onchain art and fair only where the sale makes picking pointless.
[NounsSeeder](https://github.com/nounsDAO/nouns-monorepo/blob/master/packages/nouns-contracts/contracts/NounsSeeder.sol) hashes the previous block hash with the id; Art Blocks' [PseudorandomAtomicBasic](https://github.com/ArtBlocks/artblocks-contracts/blob/main/packages/contracts/contracts/randomizer/primitive/PseudorandomAtomicBasic.sol) mixes the same block fields.
A seed from a later block has to be read before it is forgotten; [EIP-2935](https://eips.ethereum.org/EIPS/eip-2935), live since [Pectra](https://ethereum.org/en/roadmap/pectra/), extends the window from 256 to 8,191 blocks.

Marketplaces cache.
[OpenSea's metadata update page](https://docs.opensea.io/docs/updating-metadata) names the two [ERC-4906](https://eips.ethereum.org/EIPS/eip-4906) events and the `type(uint256).max` refresh, its [storage page](https://docs.opensea.io/docs/metadata-storage) accepts `data:application/json;base64,`, and its [traits page](https://docs.opensea.io/docs/media-and-traits) defines `trait_type` and `value`.

Locks miss what was added later.
[NounsDescriptorV2](https://github.com/nounsDAO/nouns-monorepo/blob/master/packages/nouns-contracts/contracts/NounsDescriptorV2.sol) guards `addBackground` and `setPalette` with `whenPartsNotLocked` and leaves `setRenderer`, `setBaseURI` and `toggleDataURIEnabled` to the owner.

Wallet filters age badly.
[EIP-7702](https://eips.ethereum.org/EIPS/eip-7702) gives EOAs code; MetaMask's [EIP7702DeleGatorCore](https://github.com/MetaMask/delegation-framework/blob/main/src/EIP7702/EIP7702DeleGatorCore.sol) implements `onERC721Received`, so such users can receive `_safeMint` but fail a code-length filter.
[BlockSec's HypeBears report](https://blocksec.com/blog/when-safe-mint-becomes-unsafe-lessons-from-the-hype-bears-security-incident) shows the per-wallet cap bypassed from `onERC721Received` because the counter was written after `_safeMint`.

The standard surface is what indexers call.
[ERC-721](https://eips.ethereum.org/EIPS/eip-721) requires `tokenURI` to throw for an invalid id, [ERC-2981](https://eips.ethereum.org/EIPS/eip-2981) requires its interface id, and [geth](https://geth.ethereum.org/docs/fundamentals/command-line-options) and [reth](https://reth.rs/docs/reth/rpc/server_types/eth/constant.RPC_DEFAULT_GAS_CAP.html) default `rpc.gascap` to 50,000,000.

## Notes

- The checks accept any id scheme, since ids come from `Transfer` events; any attribute order and extra attributes; `image` as an SVG data URI, base64 or plain, or `image_data`; per-id or ranged ERC-4906 events; any revert reason; a `reveal` that does nothing because the design needs nothing; and a design that settles pieces inside later mints, as long as a stranger's `reveal` finishes the rest.
- The picker finds its piece through `onERC721Received` or, when ids are sequential, by guessing the next one. A same-block draw with `_mint` and non-sequential ids would slip past it. We know of no such collection.
- The freeze check reaches only the upload interface and the deployer, so a renderer or base-URI setter outside the lock, the Nouns gap, is not caught. A judge criterion over the source could be, once trials show the gap appears.
- How a design copes once the hash is gone is open. The solution draws from the next block again; Opus's trial reads the hash through OpenZeppelin's `Blockhash` library, which falls back to the EIP-2935 history contract, and redraws after that window. `test_lonePieceStillFinishes` asks only that a stranger's `reveal` finishes the piece without a revert and that a late revealer gets no say, and it does not deploy the history contract, so a design that depends on it alone also needs a path for after 8,191 blocks.
- The brief behind this task said OpenSea ignores royalties without `supportsInterface(0x2a55205a)`. We could not confirm it: Manifold's Royalty Registry probes `royaltyInfo` directly and OpenSea's creator earnings article describes settings in its Studio. The check asserts the id because ERC-2981 requires it.
- There is no chain sidecar. The agent's `foundry.toml` sets `evm_version = "prague"`; the verifier's fresh project uses Forge's default, which is Prague on the image's Foundry, so `vm.signAndAttachDelegation` and 23-byte account code work in both.
- OpenZeppelin 5.7.0 in `lib/` has `Strings.escapeJSON`, `Base64`, `ERC2981` and `IERC4906`, so nothing needs installing.
- The checks run the deploy script the way `forge script` does and set `PRIVATE_KEY` and `DEPLOYER_PRIVATE_KEY`, so an ordinary script works unchanged.
