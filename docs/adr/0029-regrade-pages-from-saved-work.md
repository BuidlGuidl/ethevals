---
status: accepted
---

# Regrade pages from saved work

A page trial leaves code, and its tests start their own chain copy.
Changing those tests can check the saved code without another model call.
The next check changes affect 36 pages across nine models.
Sixteen of 52 saved page trials changed `package.json`, so restoring source alone cannot reproduce their builds.
Two of 16 saved swap pages wrote their setup's random treasury address into the code.
A fresh address can fail those pages for a change they never saw.

## The decision

- A Build task that saves `/workspace` can regrade its saved work in a fresh trial environment.
  Contract Build tasks keep their existing regrade path.
  The runner reads artifact declarations, without a task list or a new task setting.
- The saved work replaces the agent step in a normal trial.
  Harbor builds the environment, starts the chain, runs setup, and applies its network rules as usual.
  The same verifier, judge settings, cost recording, and secret check apply.
  The restore step calls no model.
- The restore step replaces saved files and installs dependencies from the saved lockfile.
  It preserves excluded files, including the link to the fresh chain context.
- Saved public chain context supplies setup values over the fresh context.
  The fresh RPC URL stays in place.
  Harbor writes those values through the existing chain service, where the public volume is writable.
  For older rows, matching fields in `verifier/fixture.json` supply those values.
  Each regrade saves the public context for the next regrade.
- Judge-only changes use saved judge input when the judge needs no live session.
  Browser judges use the fresh trial environment too.
  Other test or verifier changes use the fresh trial environment.
  Artifact changes, instruction changes, and environment changes keep their reruns.

## Considered options

- Harbor's `trial regrade` requires a separate verifier for these trials.
  ADR 0011 rejected separate verifiers for chain tasks because they lose the chain before checking it.
- A second container setup duplicates the normal trial path and can diverge from it.
- A per-task list repeats information already present in artifact declarations.
- Restoring only the code loses added dependencies and random setup values.

## Known gaps

- Partly saved Build environments still need reruns.
- Act tasks need their chain state, which the saved files do not contain.
- Saved public context cannot recreate the contracts at `voting-page`'s random addresses.
  Replaying those deployments needs a separate decision.
