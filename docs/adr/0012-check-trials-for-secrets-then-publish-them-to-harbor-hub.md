---
status: accepted
---

# Check trials for secrets, then publish them to Harbor Hub

[ADR 0010](0010-run-tasks-on-harbor.md) accepts that the plan token or API key sits in the agent's container.
So an agent can put a secret into its trajectory or into a file it leaves, and paid CI publishes those files.
On Inspect, the board also bundled a viewer that opened every result as a readable trajectory.
Harbor's viewer is a server that reads job folders, so it can't be bundled into a static site, and the board's link opened raw JSON.
This ADR adds a secret check before anything is published, and publishes each paid trial to Harbor Hub, Harbor's own place for job results.

## Nothing secret is published

- **Every trial file is checked before it leaves the machine that ran it.** That covers the CI artifact, the release assets, and the Hub upload. The check runs where the secret values still exist, which in CI is the step that ran the trial.
- **The secrets come from config,** not from a list in code:
  - each agent's credentials in the job config, and any setting it takes from a host variable
  - the judge key
  - each task's host variables
  - the tokens inside a Codex login file

  A literal setting, such as a base URL, counts only when its name looks like a credential.
- **A trial that contains one is withheld.** Its raw files stay on that machine. Its row is an error that names the variable, never the value, and the run tells a maintainer to rotate it.

## Trials open on Harbor Hub

- **Each paid trial's Harbor job folder is uploaded to Harbor Hub,** public and owned by the `buidlguidl` org, after the check passes for the whole folder.
- **The board links each trial to its Hub page,** built from Harbor's own job and trial ids. The trajectory JSON stays a release asset, as our own copy and as the link when an upload didn't happen.
- **Only the upload step holds the Hub key.** The agent's step never has it, and a task can't name it.
- **A failed upload never fails a trial** and never schedules another paid trial.
- **Local runs upload only when asked,** because the upload is public.

## Known gaps

- **The check finds exact values only.** It misses a secret that the agent encoded or transformed, and a credential the run didn't know about.
- **Harbor Hub is a third-party service.** If it goes away, the board's links fall back to the release copies.
- **The upload publishes more than the trajectory:** agent logs, verifier output, artifacts, and Harbor's config and lock. The check covers all of it.

## Considered options

- **Render trajectories on our own site.** That's a viewer to build and keep working, which ADR 0002 set out to avoid.
- **Only `harbor view`, locally.** It works for maintainers, but readers of the board get no full view.
- **Private uploads shared with the org.** Readers of the board couldn't open them.
