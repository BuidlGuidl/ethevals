# Free checks on pull requests, paid runs after merge

A pull request runs only checks that cost nothing:

- The folder matches the format, and `compose.yaml` follows the rules in [ADR 0004](0004-evals-bring-their-own-services.md).
- The reference solution passes every test, target, and check script.
- The untouched workspace fails them, which proves the scorer isn't passing empty work.

A reviewer reads `rubric.md` in the pull request. No grader runs.

After merge, CI runs every combination of eval hash, agent, and mode that has no results yet, and opens a pull request with the new results rows.

Two things force this split. GitHub Actions gives no secrets to workflows triggered from forks, and outside teams open pull requests from forks. Paid runs on every push would also pay again for each fix.

Build and act evals must ship a reference solution in `scorer/solution/`. Without one, a broken test surfaces only after every agent has paid to fail it.

The cost: an eval's first scores arrive after merge, and a bad rubric shows up only in paid runs. Fixing the rubric changes the eval hash, so CI reruns only that eval.
