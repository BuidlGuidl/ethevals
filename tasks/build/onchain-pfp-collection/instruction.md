We're a three-person studio launching a 1,000-piece generative PFP collection, and we want it fully
onchain. our artist drew the parts as SVG fragments in a few layers and named every trait herself. her
upload script already talks to the contract through src/interfaces/IArtUpload.sol: she loads the layers
and parts from her wallet and opens the mint when she's done. each piece gets its traits from a random
draw when it's minted and the contract builds the SVG from the stored parts. rarity matters to our
collectors, so nobody should be able to pick their traits, and it has to run by itself, no oracles or
outside services. free public mint, two per wallet, and our mint page talks to it through
src/interfaces/IMintPage.sol. she can still fix a part until the last piece is minted; after that the art
is final for good, for us too. 5% royalty on secondary sales goes to her. it must show up right on
OpenSea, images, traits and royalty. put the collection in src/PFPCollection.sol as PFPCollection and a
deploy script in script/Deploy.s.sol whose run(artist) returns the collection address. we're on foundry
with solidity 0.8.30, OpenZeppelin 5.7.0 is in lib/.
