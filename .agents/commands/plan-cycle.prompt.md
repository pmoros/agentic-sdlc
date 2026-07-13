---
agent: agent
description: Run a planning ceremony — prioritize ready work, break down large items, fold in retro actions, and produce a dated roadmap doc in planning/ with owners and target dates.
---

# Plan Cycle

Facilitate a planning ceremony and capture the outcome as a dated roadmap in
`<work>/planning/`. `<work>` is the sibling `../work-sessions`
repo. Planning is where priority meets capacity — decide *what* gets picked up
next and *break down* anything too big to pick up.

## Step 1 — Establish the inputs

Read:
- `<work>/work/backlog.json` — candidate work (focus on `ready`; note
  high-priority items still in `grooming`).
- `<work>/work/wip.json` — current load (planning must account for in-flight
  work, not just new work).
- `<work>/work/WORK_STATE.md` — stale/blocked/next-actions snapshot. If it's
  stale, run `#review-backlog` and `#review-wip` first.
- The most recent `<work>/retros/*.md` — carry its open action items into this
  plan.

Ask the user for the **cycle length / horizon** (e.g. next 2 weeks) and any
**fixed commitments or dates** (scheduled changes, deadlines, on-call).

## Step 2 — Prioritize

Rank candidate items by **priority** (Jira scale) and business impact, tempered
by dependencies and blockers. Surface conflicts explicitly (two `Critical`
items, one person). Recommend a rank; let the user adjust.

## Step 3 — Break down large items

For every `L`/`XL` item selected for the cycle, propose a breakdown into
smaller, independently-shippable pieces (each ideally `S`/`M`). Big
undecomposed items hide risk and stall. For each new sub-item, offer to create
a `backlog.json` entry and/or a Jira sub-task (guarded). For the Jira write,
load `.agents/rules/atlassian.instructions.md` first — it is not auto-loaded
and covers the Epic-link/parent quirks.

## Step 4 — Capacity check

Compare the selected work against realistic capacity given current WIP. If the
plan exceeds capacity, say so and recommend what to defer. Don't plan a cycle
that's already overloaded — that's how items go stale.

## Step 5 — Write the plan doc

Write `<work>/planning/<YYYY-MM-DD>-<slug>.md`:

```markdown
# Plan — <cycle / horizon>

**Date:** <YYYY-MM-DD>
**Horizon:** <e.g. 2026-07-02 → 2026-07-16>
**Planned by:** <who>

## Goals for the cycle
- 

## Committed work (prioritized)
| Rank | ID | Title | Priority | Weight | Owner | Notes |
|---|---|---|---|---|---|---|

## Breakdowns created
- <parent ID> → <new sub-item IDs + titles>

## Carried-over retro actions
- <action> — <tracking ID>

## Deferred / not this cycle
- <ID> — <why deferred>

## Risks & dependencies
- 
```

## Step 6 — Reflect into the tracker

- Set `roadmap` entries (step, owner, `target_date`, type) on the committed
  items in `backlog.json` so `WORK_STATE.md`'s "Next actions" reflects the plan.
- Append a `history` note to items whose priority/breakdown changed.
- Re-run `#review-backlog` to regenerate `WORK_STATE.md` counts.

Confirm the plan path and give a one-paragraph summary: cycle goals, top
committed items, what was deferred and why. Note that items can now be picked
up via `start-work-session` in priority order.
