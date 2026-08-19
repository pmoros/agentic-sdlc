---
agent: agent
description: Backlog health check — stale/outstanding items, grooming aging, Jira status mismatches, roadmap gaps; regenerate WORK_STATE.md. Optionally sync from Jira first.
---

# Review Backlog

Assess whether the backlog is on track and regenerate the derived snapshot in
`<work>/work/WORK_STATE.md`. `<work>` is the sibling
`../work-sessions` repo.

## Step 1 — Load state

Read `backlog.json`, `wip.json` (generated views over `work/items/*.json` —
read-only, `{title, status, priority, scope}` per id only; see Step 2 for how
writes actually happen), `scratchpad.json`, `INBOX.md`, and the current
`WORK_STATE.md`. Compute ages against today's date (provided in context).

Neither generated view carries `roadmap`, `history`, or `current_state` — for
Step 3's roadmap-gap and blocked-item analysis, read each relevant id's own
`work/items/<id>.json`.

## Step 2 — Optional Jira sync

Ask (or honor an explicit `--sync` argument): "Sync from Jira first?" If yes,
load `.agents/rules/atlassian.instructions.md` for the field/status contract,
then query `assignee = currentUser() AND resolution = Unresolved` and
reconcile:
- **New in Jira, not tracked** → create it via `scripts/define-work-item.sh
  <id> --description "..." --status ready --ticket <url>
  --record-event "Synced from Jira" --by "#review-backlog"
  --work-sessions-repo <path>` (or match the live Jira status if not
  actually ready). Never hand-write `backlog.json` — it's regenerated.
- **Tracked status disagrees with Jira** → record under "Status mismatches" in
  `WORK_STATE.md`. Do **not** auto-correct — a human picks the accurate one.
- **Done/closed in Jira but still open here** → flag for closing; don't delete
  silently.

## Step 3 — Health analysis

Evaluate against the heuristics (state the thresholds you used):
- **Stale grooming** — items in `grooming` for more than 30 days, per each
  item's own `work/items/<id>.json` `history` (age isn't in `backlog.json`).
- **Outstanding/aging** — `ready` items that have sat un-picked-up a long time
  (candidates to drop, re-prioritize, or schedule), same per-item `history`
  read.
- **Roadmap gaps** — from each item's own `work/items/<id>.json` (not
  `backlog.json`, which has no `roadmap` field): items whose `roadmap` is
  empty or whose `target_date` is `TBD` (no dated commitment) or already in
  the past (overdue).
- **Unshaped load** — count of untriaged `INBOX.md` lines (pending
  `#triage-inbox`).
- **Priority/scope sanity** — any `L`/`XL` items that should be broken down;
  any high-priority items still stuck in `grooming`.
- **Hierarchy roll-up (ADH-012)** — from the same per-item reads Step 3
  already does (`parent_id` lives on the child only — no extra pass): for
  every item in this scan that's a parent, note its done/total count (e.g.
  "3/5 sub-items done"); for every child, note its parent. Read-only,
  informational — never written back to `WORK_STATE.md`'s source items.

## Step 4 — Regenerate WORK_STATE.md

Rewrite `WORK_STATE.md` preserving its section structure:
- **Snapshot** counts (backlog / WIP / scratchpad / untriaged inbox).
- **Stale items**, **Blocked items** (derived from each item's own
  `current_state.is_blocked` — read from `work/items/<id>.json`, not the
  generated view), **Status mismatches**, **Next actions** (pulled from each
  item's own `roadmap`, nearest dated `target_date` first).
- Keep it a *snapshot* — the JSON files remain the source of truth. Note the
  date of this refresh.

## Step 5 — Readout

Give a short verdict: **is the backlog on track?** Lead with the 2–3 things
that need attention now (e.g. "5 items untriaged; 2 high-priority items still
in grooming; PROJ-6491 status disagrees with Jira"). Offer the natural next
step — `#triage-inbox`, `#groom-item <id>`, or `#plan-cycle`.
