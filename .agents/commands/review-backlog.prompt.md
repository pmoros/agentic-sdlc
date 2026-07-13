---
agent: agent
description: Backlog health check — stale/outstanding items, grooming aging, Jira status mismatches, roadmap gaps; regenerate WORK_STATE.md. Optionally sync from Jira first.
---

# Review Backlog

Assess whether the backlog is on track and regenerate the derived snapshot in
`<work>/work/WORK_STATE.md`. `<work>` is the sibling
`../work-sessions` repo.

## Step 1 — Load state

Read `backlog.json`, `wip.json`, `scratchpad.json`, `INBOX.md`, and the current
`WORK_STATE.md`. Compute ages against today's date (provided in context).

## Step 2 — Optional Jira sync

Ask (or honor an explicit `--sync` argument): "Sync from Jira first?" If yes,
load `.agents/rules/atlassian.instructions.md` for the field/status contract,
then query `assignee = currentUser() AND resolution = Unresolved` and
reconcile:
- **New in Jira, not tracked** → add to `backlog.json` as `ready` (or match the
  live Jira status), with a `history` entry noting the sync.
- **Tracked status disagrees with Jira** → record under "Status mismatches" in
  `WORK_STATE.md`. Do **not** auto-correct — a human picks the accurate one.
- **Done/closed in Jira but still open here** → flag for closing; don't delete
  silently.

## Step 3 — Health analysis

Evaluate against the heuristics (state the thresholds you used):
- **Stale grooming** — items in `grooming` for more than 30 days.
- **Outstanding/aging** — `ready` items that have sat un-picked-up a long time
  (candidates to drop, re-prioritize, or schedule).
- **Roadmap gaps** — items whose `roadmap` is empty or whose `target_date` is
  `TBD` (no dated commitment) or already in the past (overdue).
- **Unshaped load** — count of untriaged `INBOX.md` lines (pending
  `#triage-inbox`).
- **Priority/weight sanity** — any `L`/`XL` items that should be broken down;
  any high-priority items still stuck in `grooming`.

## Step 4 — Regenerate WORK_STATE.md

Rewrite `WORK_STATE.md` preserving its section structure:
- **Snapshot** counts (backlog / WIP / scratchpad / untriaged inbox).
- **Stale items**, **Blocked items** (derived from `current_state.is_blocked`),
  **Status mismatches**, **Next actions** (pulled from each item's `roadmap`,
  nearest dated `target_date` first).
- Keep it a *snapshot* — the JSON files remain the source of truth. Note the
  date of this refresh.

## Step 5 — Readout

Give a short verdict: **is the backlog on track?** Lead with the 2–3 things
that need attention now (e.g. "5 items untriaged; 2 high-priority items still
in grooming; PROJ-6491 status disagrees with Jira"). Offer the natural next
step — `#triage-inbox`, `#groom-item <id>`, or `#plan-cycle`.
