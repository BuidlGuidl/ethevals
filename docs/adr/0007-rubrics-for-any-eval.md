---
status: accepted
---

# Allow a rubric on any eval

Any eval can add a rubric after its target, tests, or check script.
Builds show the grader the compiled source, so an agent cannot hide code from grading.
Other evals show the agent's transcript, including tool calls, their results, and the final reply.
Evidence stays capped at 100,000 bytes. Free checks skip rubrics.
The total epoch limit leaves room for the scorer deadlines within Inspect's scoring window.

Plans check the budget, without a wall-time window or deferred epochs.
Each epoch keeps its Inspect working, total, and scoring limits. CI stops the job after six hours.
