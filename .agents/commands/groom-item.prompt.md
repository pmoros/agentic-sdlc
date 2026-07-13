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
given, read `<work>/work/backlog.json`, list all items with status `grooming`,
and ask which to groom (or offer to groom the highest-priority one).

## Step 2 — Load context

- Read the item from `backlog.json` (or `wip.json`/`scratchpad.json`).
- If it has a Jira/GitHub ticket, read the live issue (reads need no approval)
  for the authoritative description, acceptance criteria, and comments. Follow
  `.agents/rules/atlassian.instructions.md` for Jira reads.
- If the item references docs/PRs/dashboards, skim them enough to judge whether
  they actually answer the open questions.

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
7. **Size sanity** — is the `weight` still right? If `L`/`XL`, recommend
   breaking it into smaller items at planning.

## Step 4 — Verdict

Produce one of:

- **READY** — all of why/what/AC/test-scenarios are clear and no blocking gaps.
  Update the item: `status: "ready"`, refresh `current_state.description`,
  append a `history` entry ("Groomed to ready", ISO timestamp, `by`). If the
  weight or priority changed, update them too.
- **NOT READY** — keep `status: "grooming"` and produce a precise, actionable
  gap list ("Needs: explicit AC; owner for the FSx credentials; confirmation
  of target region"). Append a `history` entry recording the grooming pass and
  what's outstanding. Where the fix is a question for a specific person/team,
  say who to ask.

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
