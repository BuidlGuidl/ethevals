# Royalty after burn

This quiz asks what OpenZeppelin 5.7's `ERC721Royalty` reports for a token whose per-token royalty was set, then burned, then minted again.
The fixed answer is the per-token royalty.
OpenZeppelin 4 cleared it in `_burn`, and a model trained on that code answers "default".

## The instruction

> Our collection uses OpenZeppelin Contracts 5.7's ERC721Royalty. We set a per-token royalty on token 7 with _setTokenRoyalty, later burned token 7, and then minted token 7 again. Does royaltyInfo(7, price) now use that per-token royalty or the default royalty? Answer per-token or default, then explain in one sentence.

## What it touches

- ERC-2981 in OpenZeppelin 5. `ERC721Royalty` only merges `supportsInterface`; nothing hooks the burn. A per-token royalty set once applies to whoever holds that id later.
- Re-minting ids. A collection that burns and re-mints, or that reuses ids after a burn, carries royalty settings it may not expect.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `royalty_after_burn` | The reply starts with "per-token", ignoring case, a leading "the", and leading punctuation | ERC-2981 |

The check accepts "per token" and "per-token" and checks the fixed answer without judging the explanation.
The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A platform that lets creators set a per-token royalty, burn, and re-mint sends the next owner's sales to the old recipient unless it resets the royalty itself.
OpenZeppelin's [5.0.0 changelog](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/CHANGELOG.md) records that `ERC721URIStorage` and `ERC721Royalty` stop resetting on burn, [`ERC721Royalty.sol` in 5.7.0](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/contracts/token/ERC721/extensions/ERC721Royalty.sol) has no burn hook, and [the 4.9.6 version](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v4.9.6/contracts/token/ERC721/extensions/ERC721Royalty.sol#L34-L37) called `_resetTokenRoyalty` from `_burn`.
