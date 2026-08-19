# 0003 — Reconcile ADR-0002 with the ADH-008 Work Item Store

| Field | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-08-19 |
| **Deciders** | Paul Moros (pending) |
| **Tags** | work-sessions, work-items, concurrency, git-worktree, session-state, data-integrity |

## Context

ADR-0002 ("Per-Session Isolation of `work-sessions` State," `IO-254`,
Accepted 2026-08-18) and the `ADH-008-decouple-control-exec` session were
developed **concurrently, in separate worktrees, unaware of each other**.
Both diagnose overlapping symptoms — `SESSIONS_STATE.md` and
`work/wip.json` silently missing rows for genuinely-active sessions — and
both propose the same shape of fix: collapse a hand-synced, racy
three-way status view into one authoritative per-item/per-session file,
with the shared aggregates (`SESSIONS_STATE.md`, `work/wip.json`)
regenerated from it rather than hand-edited.

They propose **different, incompatible upstream sources of truth** for
that regeneration:

| | ADR-0002 (as written) | ADH-008 (built, tested, live-migrated this session) |
|---|---|---|
| Root cause named | Single shared `work-sessions` checkout; a `git checkout` in it can strand another session's uncommitted state | `lib/upsert_wip.py` had no locking — a plain concurrent read-modify-write race |
| Source of truth | `sessions/<id>/state.json` (new; lean — `status`/`title`/`tickets[]`/`created`/`last_change`/`blockers`/`task_type`/`scope`) | `work/items/<id>.json` (built; richer — adds `description`, `current_state`, append-only `history`, `roadmap`, `sessions[]`, `last_synced`) |
| Aggregate regenerator | `regenerate-sessions-state.sh` (proposed, not built) | `regenerate-views.sh` (built, tested) |
| Concurrency mechanism | Per-session `work-sessions` git worktree + branch (`session/<id>`) — protects against a shared *checkout* being switched under a writer | Per-item `mkdir`-lock (`work/items/<id>.json.lock/`) — protects against concurrent *processes* racing the same file |

**Neither addresses the other's failure mode.** ADH-008's per-item lock
does nothing to stop a `git checkout` in the shared `work-sessions`
checkout from stranding another session's uncommitted files — that class
of incident is exactly what ADR-0002's Part 1 (per-session worktree)
exists to prevent, and ADH-008 never considered it at all. Conversely,
ADR-0002's worktree isolation does nothing to prevent two writers on the
*same branch* from racing the same JSON file — that's what ADH-008's lock
is for. **Both incidents are real** — a live lost-update on `wip.json`/
`SESSIONS_STATE.md` was found and repaired during `ADH-008` Phase 7
(`ADH-008-decouple-control-exec` and `IO-234-block-bedrock-scp` both
silently vanished from the registry), consistent with either or both root
causes; `work-sessions` was also observed to have never actually been
git-committed during this session, which is squarely ADR-0002's diagnosis.

As written, implementing ADR-0002 would create a **second, competing
regenerator** for `SESSIONS_STATE.md`/`work/wip.json`, sourced from a
thinner, redundant per-session file sitting alongside the richer
`work/items/<id>.json` this session already built, tested, and used to
migrate all 21 real live items.

ADR-0002's Parts 1 and 3 (per-session `work-sessions` worktree; `main` as
the single writer of the aggregate via a `sync-sessions-state` step) are
**not implemented yet** (confirmed 2026-08-19: no `regenerate-sessions-state.sh`,
no `state.json` anywhere, no `work-sessions.worktrees/` sibling, no rule in
`AGENTS.md`, `session-template/` unchanged) — so nothing built conflicts
with anything live today. This ADR is a proposal to reconcile the two
designs before that implementation work happens, not a report of a live
collision.

## Decision

**Amend ADR-0002's Part 2** ("One per-session source of truth; the
aggregate is generated") to consume the already-built `work/items/<id>.json`
instead of inventing `sessions/<id>/state.json`. Keep ADR-0002's Parts 1
and 3 as designed — they address a real gap ADH-008 never touched.

Concretely, for whoever implements ADR-0002 next:

1. **Drop `sessions/<id>/state.json`.** `work/items/<id>.json`
   (`scripts/lib/define_work_item.py` / `scripts/define-work-item.sh`) is
   the per-item source of truth going forward — richer than the originally
   proposed shape, and it already has the `sessions[]` field ADR-0002's
   own future episode-tracking would need anyway.
2. **Unify the regenerators.** `regenerate-sessions-state.sh` (ADR-0002,
   unbuilt) and `regenerate-views.sh` (ADH-008, built) should not both
   exist — fold ADR-0002's `SESSIONS_STATE.md` regeneration into
   `regenerate-views.sh` (or a renamed successor), scanning
   `work/items/*.json` for both outputs. `work/backlog.json` stays
   untouched by this (ADR-0002 Neutral consequence, unaffected either way).
3. **The two concurrency mechanisms protect different things — neither
   substitutes for the other, and combining them does NOT close every gap.**
   (Corrected from this ADR's first draft, which claimed the `mkdir`-lock
   provides cross-worktree "defense in depth" — it mechanically cannot: a
   `git worktree` gives each session its own physical directory, so two
   worktrees' `work/items/<id>.json.lock` paths are never the same path and
   can never contend. The lock only protects concurrent *processes sharing
   one checkout* — exactly ADH-008's original scope, e.g. two things writing
   the same item within the single shared `work-sessions` checkout today, or
   within whatever single checkout `sync-sessions-state` (Part 3, below)
   runs from.
   The **real** cross-worktree hazard once Part 1 lands is a **git merge
   conflict**: if two session branches (e.g. two episodes of the same item,
   or two unrelated sessions that both groomed the same portfolio item)
   both modify the same `work/items/<id>.json`, merging both into `main`
   produces an ordinary git conflict on that file's content — not a race,
   but a real design gap this ADR does not resolve. Whoever implements
   ADR-0002 Part 3 needs to decide how `sync-sessions-state` handles that
   case (serialize per-item merges through one point and rely on git's
   normal conflict resolution; detect and flag it for a human; or something
   else) — this is genuinely open, not "already handled by layering."
4. **Adopt ADR-0002's Part 3 as-is**: `main` as the single writer of the
   generated aggregate via a `sync-sessions-state` step; the "agents never
   `git checkout`/`git switch` in the canonical `work-sessions` checkout"
   rule in `AGENTS.md`. ADH-008 has no competing opinion here.

This ADR does **not** implement any of the above — Parts 1/3 of ADR-0002
remain a real, separate, unimplemented body of work. It only resolves
which file Part 2 is built against, so that work doesn't start from a
design that's already stale relative to what ADH-008 shipped.

## Consequences

### Positive
- Avoids a second, competing per-session/per-item data file and a second,
  competing regenerator claiming the same output files.
- ADH-008's already-tested constructor, locking, and the real 21-item
  migration already run against the live `work-sessions` repo remain valid
  — they become an input to ADR-0002's future git-isolation layer instead
  of being made obsolete by it.
- `work/items/<id>.json`'s richer shape (`history`, `roadmap`, `sessions[]`)
  gives ADR-0002's future episode/session tracking more to build on than
  the originally-proposed lean `state.json` would have.

### Negative / Trade-offs
- Whoever implements ADR-0002 next must read this ADR first — the original
  Part 2 section, read alone, now describes a shape that won't be built.
- Neither ADR-0002's Parts 1/3 nor this reconciliation are implemented —
  the "orphaned commit from a shared checkout switch" failure class ADR-0002
  targets is still live and unaddressed; this ADR only prevents the two
  designs from colliding when someone does pick that work up.
- `ADH-008-decouple-control-exec`'s branch was cut before ADR-0002 merged
  to `main` — they'll need a real merge (not just a fast-forward) when this
  session's work lands, since both touched `session-state.instructions.md`-
  adjacent territory independently.
- **This ADR does not resolve cross-worktree item-file merge conflicts**
  (see the corrected Decision point 3) — that's real, unsolved design work
  for whoever builds ADR-0002 Part 3's `sync-sessions-state` step, not
  something the per-item lock already covers. Flagging it here is meant to
  prevent that implementer from assuming it's handled.

### Neutral
- `work/backlog.json` stays a hand-maintained, single-writer-on-`main`
  portfolio file either way — untouched by both designs.

## Alternatives Considered

**A — Implement ADR-0002 exactly as written, alongside ADH-008.** Rejected:
produces two regenerators racing to own `SESSIONS_STATE.md`/`work/wip.json`
from two different source files — reintroduces the exact class of drift
both designs exist to eliminate, just one layer up.

**B — Treat ADH-008 as fully superseding ADR-0002.** Rejected: ADR-0002's
git-level worktree-per-session isolation (Parts 1/3) addresses a real,
observed failure mode (orphaned commits from a shared checkout switch)
that ADH-008 never considered. Discarding it would leave that incident
class unaddressed.

**C — Leave the conflict undocumented for a future session to discover.**
Rejected: both are real, both are Accepted/built-against, and the
collision is entirely avoidable by naming it now, before either
`regenerate-sessions-state.sh` or a `sessions/<id>/state.json` migration
gets built against a design that's already stale.

## References

- ADR-0002 — `02-adrs/0002-per-session-work-sessions-isolation.md`
- `work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md` §1 (the
  `work/items/<id>.json` design this ADR proposes ADR-0002 consume)
- `work-sessions/sessions/ADH-008-decouple-control-exec/docs/gate-a-review-r1.md`
  (the per-item locking design this ADR treats as complementary to, not
  competing with, ADR-0002's worktree isolation)
