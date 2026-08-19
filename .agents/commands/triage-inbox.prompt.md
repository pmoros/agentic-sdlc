---
agent: agent
description: Triage raw INBOX.md captures into shaped backlog.json items — assign priority, weight, and a first readiness read. Part of the project-manager SDLC flow.
---

# Triage Inbox

Turn unsorted captures in `<work>/work/INBOX.md` into properly shaped work
items in `<work>/work/backlog.json`. `<work>` is the sibling
`../work-sessions` repo. Session/tracking file writes are
autonomous; Jira/GitHub writes need approval.

## Step 1 — Load state

Read, in order:
- `<work>/work/INBOX.md` — the raw captures (newest on top).
- `<work>/work/backlog.json` and `<work>/work/wip.json` — generated views;
  read-only, so you don't duplicate an item that already exists. Never edit
  these directly (see Step 3 — `define-work-item.sh` is the only writer).

If `INBOX.md` has no entries below the header, report "Inbox is empty — nothing
to triage" and stop.

## Step 2 — Classify each inbox line

For each capture, decide one of:
- **Backlog item** — a real piece of work. Shape it (Step 3).
- **Scratchpad** — ad-hoc/exploratory, no ticket and no commitment → add to
  `scratchpad.json` instead, then remove the inbox line.
- **Drop** — turned out to be a non-issue / duplicate / already done. Note why,
  then remove the inbox line.

Ask the user only when a capture is genuinely ambiguous (real work vs. noise);
otherwise use your judgment and report your classification.

## Step 3 — Shape each backlog item via the canonical constructor

Every item is created/reshaped through `scripts/define-work-item.sh` —
**never** by hand-writing JSON. Hand-shaping is what caused the historical
`scope`/`weight` field-name drift between this command and the session-start
path; the constructor is the fix (ADH-008 — see `SPEC.md` §1, §3 in
`sessions/ADH-008-decouple-control-exec/`).

For each new item, determine:

- **ID** — the Jira key if one exists (e.g. `PROJ-1234`); otherwise the next
  `ADH-NNN` (scan `backlog.json`, `wip.json`, `scratchpad.json`, and
  `SESSIONS_STATE.md` for the highest `ADH-NNN` and increment).
- **description** — what's going on and why it matters. Preserve any open
  questions from the capture as an explicit "Open Qs:" list.
- **status** — `grooming` (default). Only use `ready` if the capture already
  contains a clear why/what + acceptance criteria (rare from raw inbox).
- **priority** — record in the item (see priority note below). Ask the user if
  it's non-obvious and material.
- **scope** — `XS | S | M | L | XL` effort estimate. Flag `L`/`XL` for
  breakdown at planning.
- **ticket** — carry over a ticket link from the capture, if any.

Then run, from the `agentic-sdlc` tools worktree:

```bash
scripts/define-work-item.sh <ID> \
  --description "<description>" --status <grooming|ready> \
  --priority "<priority>" --scope <XS|S|M|L|XL> [--ticket <url>] \
  --record-event "Triaged from INBOX" --by "#triage-inbox" \
  --work-sessions-repo <work-sessions-repo-path>
```

This writes `work/items/<ID>.json` and automatically regenerates
`backlog.json`/`wip.json`/`archive.json` — never write those views by hand.
`title` is auto-seeded from `--description`; pass `--title` explicitly only
if the seeded one reads badly. Multiple `work_items`/`resources` links from
a capture (beyond a single ticket) don't have a constructor flag yet — note
them in the description, or file a follow-up to extend the constructor.

### Priority scale
Use the Jira scale: `Trivial · Minor · Major · Critical · Blocker · Emergency`
(default `Minor`). See `.agents/rules/atlassian.instructions.md`. Priority
(urgency) and scope (effort) are independent — a `Blocker` can be `XS`.

## Step 4 — Clean up

- Remove each processed line from `INBOX.md` (leave the header and format note).
- Scratchpad items go directly into `work/scratchpad.json` (unchanged —
  explicitly out of scope for the item store; see `SPEC.md` Constraints).
- Do **not** touch existing items' `history` — the constructor already
  guarantees this (reshaping preserves it unless `--record-event` is passed).

## Step 5 — Offer next steps

Show a short table of what you triaged (ID · title · priority · weight ·
status). Then:
- Note how many landed in `grooming` and need `#groom-item` before they're
  actionable.
- Offer to run `#review-backlog` to refresh `WORK_STATE.md` counts.
- If a triaged item should exist in Jira but doesn't, load
  `.agents/rules/atlassian.instructions.md` for the field contract, then offer
  to create it (with approval).
