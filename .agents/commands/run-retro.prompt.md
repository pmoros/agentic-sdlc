---
agent: agent
description: Run a retrospective over a period or a piece of work — what went well, what went wrong, when we should have asked for help, and concrete action items; write a dated doc to retros/.
---

# Run Retro

Facilitate a retrospective and capture it as a dated document in
`<work>/retros/`. `<work>` is the sibling `../work-sessions`
repo. Retros feed planning — every action item should be trackable.

## Step 1 — Scope the retro

Ask (or infer from the invocation) what the retro covers:
- A **time period** (e.g. "the last two weeks", a sprint), or
- A **specific piece of work** (a session, ticket, incident, or deployment).

Determine the date range and the items in scope.

## Step 2 — Gather evidence (don't retro from memory)

Pull the facts before facilitating:
- Items that reached `done` in the period (`wip.json` history, `SESSIONS_STATE.md`).
- `history` entries across `wip.json` / `backlog.json` in range — what moved,
  what stalled, what got blocked and for how long.
- Session `WORKLOG.md` files for the sessions in scope.
- Prior retros in `<work>/retros/` — check whether earlier action items were
  actually done (unclosed actions are a finding in themselves).
- Any linked incidents/deployments and their evidence.

Summarize the objective picture (throughput, blockers, cycle time, overdue
roadmap steps) before opinions.

## Step 3 — Facilitate the four questions

Work through these with the user, seeding each from the evidence:
1. **What went well** — keep doing it.
2. **What went wrong** — problems, misses, rework, surprises.
3. **When should we have asked for help (sooner)?** — items that sat blocked or
   stalled that a timelier escalation would have unblocked; where did WIP
   overload or a bottleneck hurt us? Be specific and blameless.
4. **What will we change** — concrete action items, each with an **owner** and
   a **target date**.

## Step 4 — Write the retro doc

Write `<work>/retros/<YYYY-MM-DD>-<slug>.md` using this template:

```markdown
# Retro — <scope> (<date range>)

**Date:** <YYYY-MM-DD>
**Facilitator:** <who>
**Scope:** <period or work item(s)>

## Snapshot
<Objective numbers: items completed, still open, blocked days, overdue roadmap steps.>

## What went well
- 

## What went wrong
- 

## When we should have asked for help
- <situation> — <what a timelier ask would have changed>

## Action items
| Action | Owner | Target date | Tracking |
|---|---|---|---|
|  |  |  | <backlog ID / ticket, or "to create"> |

## Follow-up on previous retro actions
- <prior action> — done / not done / carried over
```

## Step 5 — Close the loop into the backlog

For each action item, offer to create a tracking entry so it isn't lost:
- Add it to `<work>/work/backlog.json` (status `grooming`, an `ADH-NNN` ID or a
  real ticket), or
- Create a Jira ticket (guarded write — needs approval).

Confirm the retro path and list the action items with their tracking IDs. Note
that these actions should be considered in the next `#plan-cycle`.
