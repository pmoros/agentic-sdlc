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

**Hierarchy roll-up (ADH-012)** — while ranking, you're already reading each
candidate's own `work/items/<id>.json` (for priority/dependencies above); no
second pass is needed. For any candidate that is a parent (another loaded
item's `parent_id` points at it) or a child (has its own `parent_id`), show
one roll-up line alongside its normal rank row: a parent gets its
done/total count (e.g. "3/5 sub-items done"), a child names its parent.
Read-only — nothing here is written back to any item.

## Step 3 — Break down large items

For every `L`/`XL` item selected for the cycle, propose a breakdown into
smaller, independently-shippable pieces (each ideally `S`/`M`). Big
undecomposed items hide risk and stall. For each new sub-item, offer to
create it via `scripts/define-work-item.sh <id> --description "..." --status
grooming --scope <XS|S|M|L|XL> [--priority ...] --parent <parent-id>
--work-sessions-repo <path>` (`backlog.json` is a generated view, never
hand-written) and/or a Jira sub-task (guarded). `--parent` (ADH-012) is what
makes this a real, queryable link in the item store — not just the prose
record in this cycle's plan doc (below) — and is validated before any write
(refuses a two-level chain, a nonexistent parent, or linking an item that's
already a parent itself; exactly one level of nesting is supported). For the
Jira write, load `.agents/rules/atlassian.instructions.md` first — it is not
auto-loaded and covers the Epic-link/parent quirks; note that Jira's own
Epic-link relationship (if any) is entirely independent of the local
`parent_id` link — this session does not sync the two.

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

- For each item that gained a concrete planned step this cycle (ADH-014),
  record it on the item itself, not only in the plan doc's prose:
  `scripts/define-work-item.sh <id> --roadmap-step "<step text>"
  --roadmap-owner "<name>" [--roadmap-target-date <date>]
  [--roadmap-type <type>] --work-sessions-repo <path>`. `--roadmap-owner`
  is required — if the cycle didn't actually settle on an owner for a
  step, that's a real gap to raise before writing it, not something to
  default away. Append-only: this never edits or removes a past roadmap
  entry, matching `history`'s own precedent.
- For any item whose priority/scope changed, update it via
  `scripts/define-work-item.sh <id> [--priority ...] [--scope ...]
  --record-event "Re-prioritized at planning" --by "#plan-cycle"
  --work-sessions-repo <path>`.
- Re-run `#review-backlog` to regenerate `WORK_STATE.md` counts.

Confirm the plan path and give a one-paragraph summary: cycle goals, top
committed items, what was deferred and why. Note that items can now be picked
up via `start-work-session` in priority order.
