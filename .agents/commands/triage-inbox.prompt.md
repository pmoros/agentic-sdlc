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
- `<work>/work/backlog.json` and `<work>/work/wip.json` — so you don't
  duplicate an item that already exists.
- `<work>/work/template.json` — the canonical item shape to copy.

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

## Step 3 — Shape each backlog item

Copy the structure from `template.json`. For each new item set:

- **ID** — the Jira key if one exists (e.g. `PROJ-1234`); otherwise the next
  `ADH-NNN` (scan `backlog.json`, `wip.json`, `scratchpad.json`, and
  `SESSIONS_STATE.md` for the highest `ADH-NNN` and increment).
- **title** — short imperative summary.
- **description** — what's going on and why it matters. Preserve any open
  questions from the capture as an explicit "Open Qs:" list.
- **status** — `grooming` (default). Only use `ready` if the capture already
  contains a clear why/what + acceptance criteria (rare from raw inbox).
- **priority** — record in the item (see priority note below). Ask the user if
  it's non-obvious and material.
- **weight** — `XS | S | M | L | XL` effort estimate. Flag `L`/`XL` for
  breakdown at planning.
- **started** — today's date (`DD Month YYYY`).
- **history** — one entry: action "Triaged from INBOX", ISO timestamp, `by`.
- **tickets / work_items / resources** — carry over any links from the capture.

### Priority scale
Use the Jira scale: `Trivial · Minor · Major · Critical · Blocker · Emergency`
(default `Minor`). See `.agents/rules/atlassian.instructions.md`. Priority
(urgency) and weight (effort) are independent — a `Blocker` can be `XS`.

## Step 4 — Write and clean up

- Add the shaped items to `backlog.json` (or `scratchpad.json`), keyed by ID.
- Remove each processed line from `INBOX.md` (leave the header and format note).
- Do **not** touch existing items' `history`.

## Step 5 — Offer next steps

Show a short table of what you triaged (ID · title · priority · weight ·
status). Then:
- Note how many landed in `grooming` and need `#groom-item` before they're
  actionable.
- Offer to run `#review-backlog` to refresh `WORK_STATE.md` counts.
- If a triaged item should exist in Jira but doesn't, offer to create it
  (with approval, per `.agents/rules/atlassian.instructions.md`).
