Copies of Chainlink's VRF 2.5 mock and what it imports, from the `@chainlink/contracts` 1.5.0 npm package
(sha256 24a8d510e947a74763723845d5f55405997104aecb9d45061f969d25fb917a3d), all MIT.
`src/v0.8/vrf/dev/SubscriptionAPI.sol` has one change: its OpenZeppelin import points at the copy of
`EnumerableSet.sol` from OpenZeppelin Contracts 4.9.6 under `src/v0.8/vendor/`, so the verifier needs no remapping.
The tests use these copies instead of the agent's `lib/`, so the checks compile whatever the agent does to its libraries.
