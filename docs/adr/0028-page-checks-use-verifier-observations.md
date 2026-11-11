---
status: accepted
---

# Page checks use verifier observations

The Aave cap check used input events from the page to assign wallet requests to an attempt.
An unrelated input could hide an over-cap request or assign a later withdrawal to that attempt.

## The decision

The cap check requires the verifier's `full-cap` command and a successful in-room USDC deposit.
After that command, a USDC supply request above its recorded room fails the check.
A USDC approval to the Pool above that room also fails it.
The check reads the verifier's condition records and wallet log alone.
It uses the latest preceding cap record for each request.
It does not trust typing events or expose a typing endpoint.
The page judge still checks whether the page explains Aave's cap to the user.

Both page sessions wait for pending wallet writes before producing checks.
Wallet reads do not extend that wait.
A wait failure or a session error produces no reward.
The swap session combines its transaction checks in a pure function with behavior tests.
A project that fails compilation gets failed code checks and criteria without installing or running judge tools.

File judges deny shell and web tools.
Page judges keep their chain reads and condition commands.
Tests keep task-local copies equal to these two named helper variants.
Browser packages install outside the tests that RewardKit discovers.
Instructions, environments, artifact settings, and image pins stay unchanged.
