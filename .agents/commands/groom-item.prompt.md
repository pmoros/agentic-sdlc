---
agent: agent
description: Groom one backlog item to readiness — check why/what clarity, acceptance criteria, test scenarios, and missing info/docs/links; flip grooming → ready or list exactly what's blocking readiness.
---

# Groom Item

Assess a single work item for readiness so that someone else could pick it up
and know exactly what "done" means. `<work>` is the sibling
`../work-sessions` repo.

## Step 1 — Identify the item

Take the item ID from the invocation (e.g. `groom-item PROJ-6885`). If none was
given, read `<work>/work/backlog.json` (a generated view, read-only — see Step
4 for how writes actually happen), list all items with status `grooming`, and
ask which to groom (or offer to groom the highest-priority one).

## Step 2 — Load context

- Read the item from `<work>/work/items/<id>.json` (the source of truth;
  `backlog.json`/`wip.json` are read-only generated views).
- If it has a Jira/GitHub ticket, read the live issue (reads need no approval)
  for the authoritative description, acceptance criteria, and comments. Follow
  `.agents/rules/atlassian.instructions.md` for Jira reads.
- If the item references docs/PRs/dashboards, skim them enough to judge whether
  they actually answer the open questions.
- **Reconcile against existing work (avoid rework).** Search Jira (and
  `wip.json`/sessions) for tickets that **duplicate**, **supersede**, or
  **already deliver** this item. If it's a duplicate or already done, say so and
  stop — never groom a duplicate to `ready`; recommend closing/merging or
  re-statusing the existing ticket instead. Also confirm the item isn't already
  owned/in-flight under a different key.
- **Hierarchy (ADH-012)** — this is a read-only, computed display; nothing is
  written back to any item by this step:
  - If the item has a `parent_id`, read that parent's own file and show its
    title + status in one line (e.g. "Sub-item of `ADH-020` — Build the
    thing (in progress)").
  - Otherwise, scan `<work>/work/items/*.json` for any item whose
    `parent_id` equals this one's id. If any exist, list them
    (id/title/status) and a plain count (e.g. "3/5 sub-items done").

## Step 3 — Run the readiness checklist

Load `.agents/rules/dev-lifecycle.instructions.md` — `ready` is the entry
criterion for Stage 0 (Planning & Decomposition) of that pipeline, so the
checklist below should score against what Stage 0/1 actually need, not just
generic completeness. Score each dimension **clear / unclear / missing** and
cite the evidence:

1. **Why** — is the motivation / problem / business value stated? Would a
   reviewer understand why this matters now?
2. **What** — is the desired outcome / scope defined? Is it clear what is in
   scope and what is explicitly *not*?
3. **Acceptance criteria** — are they explicit and verifiable? Prefer
   `Given / When / Then` per the engineering doctrine
   (`.agents/rules/engineering.instructions.md`). Vague AC = not ready.
4. **Test / verification scenarios** — is it clear how success will be proven
   (specific commands, observables, or checks — not "looks fine")?
5. **Missing info / docs / links** — anything needed to start that isn't
   captured: access, credentials owner, runbook, dependency, related ticket,
   design decision.
6. **Dependencies & blockers** — does it depend on other items or teams? Is it
   actually blocked right now?
7. **Size sanity** — is the `scope` still right? If `L`/`XL`, recommend
   breaking it into smaller items — and, per ADH-012, this doesn't have to
   wait for `#plan-cycle`: offer to create the sub-item(s) right now via
   `scripts/define-work-item.sh <new-id> --description "..." --status
   grooming --parent <this-id> --work-sessions-repo <path>`, which links it
   as a real sub-item immediately rather than only noting the breakdown in
   prose.

## Step 4 — Verdict

Produce one of:

- **READY** — all of why/what/AC/test-scenarios are clear and no blocking gaps.
  Update the item through the canonical constructor — never hand-edit
  `work/items/<id>.json` or `backlog.json` (the latter would be silently
  overwritten by the next regeneration anyway):
  ```bash
  scripts/define-work-item.sh <id> --status ready [--scope <XS|S|M|L|XL>] \
    [--priority <priority>] --current-state "<refreshed one-line status>" \
    --record-event "Groomed to ready" --by "#groom-item" \
    --work-sessions-repo <work-sessions-repo>
  ```
  Only pass `--scope`/`--priority` if grooming actually changed them.
- **NOT READY** — keep `status: "grooming"` (omit `--status`, or pass it
  explicitly) and produce a precise, actionable gap list ("Needs: explicit
  AC; owner for the FSx credentials; confirmation of target region"). Record
  the pass the same way:
  ```bash
  scripts/define-work-item.sh <id> \
    --current-state "<one-line summary of what's outstanding>" \
    --record-event "Grooming pass — not ready: <short gap summary>" \
    --by "#groom-item" --work-sessions-repo <work-sessions-repo>
  ```
  Where the fix is a question for a specific person/team, say who to ask.

Never invent acceptance criteria to force a `ready` — surface the gap instead.

## Step 5 — Optionally enrich the ticket

If grooming produced better AC / scope / test scenarios and the item has a Jira
ticket, offer to write them back to the ticket description (guarded write —
needs approval; merge with existing description, never overwrite; follow the
Atlassian field contract).

## Step 6 — Report

Show the checklist result, the verdict, and the gap list (if any). If READY,
note it can now be picked up via `start-work-session`. Offer to groom the next
`grooming` item.
