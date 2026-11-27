---
status: accepted
---

# Weight Overall by each pillar's task count, up to 25

Overall was the plain average of the three pillar scores (ADR 0034 kept it).
The pillars are uneven for now: Concepts has 25 tasks, Build 25, and Act 3, against targets of 50, 25 and 25.
So one Act trial moved Overall by 5.6 points, while one Build trial moved it by 0.67.

## The decision

Each pillar counts by its number of tasks, up to 25.

```text
weight of a pillar = min(tasks in the pillar, 25)
Overall            = sum(weight × pillar score) ÷ sum(weight), over pillars with a score
```

| Tasks (Concepts / Build / Act) | Weights | Act's share |
| --- | --- | --- |
| 25 / 25 / 3 (today) | 25 / 25 / 3 | 3 of 53 |
| 50 / 25 / 25 (targets) | 25 / 25 / 25 | one third |

- **The cap keeps equal thirds as the design.** Without it, Concepts at 50 tasks would take half of Overall.
- **Tasks are counted from the task list in view,** all tasks or one domain's tasks, not from the tasks a configuration has scored. A configuration with errored tasks gets the same weights as everyone else.
- **Pillars without a score stay out,** as before.
- **Every Overall uses the same weights:** the leaderboard, Compare, the skill lift, and the drawer's domain scores.
- **The rule retires itself.** Once every pillar has 25 tasks, the weights are equal and Overall is the plain average again.
