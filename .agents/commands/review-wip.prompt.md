---
agent: agent
description: WIP health check — load & importance of in-flight items, on-hold-too-long, blockers, and systemic bottlenecks; recommend whether to finish, get help, or drop.
---

# Review WIP

Assess what's actively in flight and whether the team is overloaded, stuck, or
bottlenecked. `<work>` is the sibling `../work-sessions` repo.

## Step 1 — Load state

Read `<work>/work/wip.json`, `<work>/SESSIONS_STATE.md` (to correlate items
with active/paused sessions), and the current `WORK_STATE.md`. Compute ages
against today's date.

## Step 2 — Per-item read

For each WIP item, capture:
- **Importance** — priority × business impact. Rank the list.
- **Age & movement** — days since the last `history` entry. Flag **stale**
  (>7 days no movement).
- **State** — `in progress` / `on hold` / `in review`. Flag anything **on hold
  or blocked for >14 days**.
- **Blocker** — if `current_state.is_blocked`, what's it blocked on and who
  owns the unblock? Is anyone actually chasing it?
- **Session** — is there a live session/worktree, or is it "in progress" on
  paper only?

## Step 3 — Detect overload and bottlenecks

- **WIP overload** — if more than ~3–4 items are simultaneously `in progress`
  for one person, say so plainly and recommend finishing or parking the
  lowest-importance ones before starting anything new.
- **Bottleneck patterns** — look for *clusters*, not just individual items:
  - Several items stuck in the same state (e.g. all waiting on review/merge).
  - Multiple items blocked on the same team, approval, or dependency.
  - Items repeatedly bouncing between states.
  Name the bottleneck and propose the systemic fix (e.g. "3 PRs waiting on
  review — request reviewers / pair to clear the queue"), not just per-item
  nudges.
- **On hold too long** — recommend escalate, re-scope, or drop with rationale.

## Step 4 — "Do we need help?"

Make an explicit call for each at-risk item: **keep going / ask for help /
escalate / drop**. When recommending help, say *what kind* (reviewer, subject
expert, decision from a stakeholder, another pair of hands) and *from whom* if
known. This is the question the user most wants answered — don't hedge.

## Step 5 — Update derived state

Refresh the **Blocked items** and **Stale items** sections of `WORK_STATE.md`
from this pass (keep `current_state.is_blocked` in each item in sync with
reality — update it if a blocker cleared or appeared, with a `history` entry).

## Step 6 — Readout

Lead with the headline: how many in flight, how many stale/blocked, the single
biggest bottleneck, and the top recommendation. Then the ranked item list.
Offer to draft the escalation/help message, or to run `#run-retro` if a
recurring bottleneck warrants a deeper look.
