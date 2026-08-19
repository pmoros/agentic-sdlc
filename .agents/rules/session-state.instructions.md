# Session State Maintenance

> **Trigger:** read this file at session start, and whenever
> `#pause_work_session`, `#resume_work_session`, `#stop_work_session`, or
> `#end_work_session` runs — each of those commands loads it explicitly. Not
> auto-loaded — see `AGENTS.md` § Integration Schemas and
> `02-adrs/0001-tiered-conditional-rule-loading.md`. Command-triggered, so it
> has no reliable GitHub Copilot `applyTo:` glob; Copilot users open this
> file manually at those points.

While a session is active, its tracking files are **living documents** — keep
them current *as you work*, not only at lifecycle boundaries (start / pause /
stop / end). If the session were resumed cold from these files alone, they
should fully explain where things stand. All these writes are **autonomous**
— no approval needed (per the Git Policy in `AGENTS.md`: session file
read/write is autonomous).

**Identify the active session** from `work-sessions/SESSIONS_STATE.md`
(the `Status: active` row) or from the session worktree you're operating in.
State lives in two places:

- **Portfolio-level** — `work-sessions/work/`: `items/<id>.json` (the
  writable store, one file per item), `backlog.json`/`wip.json`/
  `archive.json` (generated views over it — never edit directly),
  `scratchpad.json` (separate, manually-edited, pre-item store — out of
  scope for the item model), `INBOX.md`, `WORK_STATE.md`.
- **This session** — `work-sessions/sessions/<id>/`: `CONTEXT.md`,
  `PLAN.md`, `SPEC.md`, `TASKS.md`, `WORKLOG.md`.

## What each file holds, and when to update it

| File | Holds | Update it when… |
|---|---|---|
| `TASKS.md` | Granular task table (Task / Status `todo\|in progress\|blocked\|done` / Owner / Notes) | **Continuously** — the moment a task is picked up, finished, blocked, or discovered. This is the highest-frequency file. |
| `CONTEXT.md` → *Current state* | One or two lines: where things stand right now + `Blocked: yes/no` | Whenever reality changes — blocked/unblocked, waiting on review, direction shifts. Keep it true *now*. |
| `CONTEXT.md` → *Activity log* | Append-only terse timestamped actions | On every significant action (branch/worktree/PR created, decision made, blocker hit). Append via `scripts/session-log.sh`. |
| `CONTEXT.md` → *Tickets / contacts / dates* | Live reference | When a ticket/contact/date is learned or changes. |
| `CONTEXT.md` → *Related Wiki* | `Page \| Space \| Link` table of linked Confluence pages | Asked at session start (`start-work-session` skill) and re-checked at close (`#end_work_session`) — append-only, never remove a linked page. An empty table (header row only) means asked, nothing relevant; an absent heading means the session predates this step. |
| `WORKLOG.md` | Append-only log of lifetime events | Session started/paused/resumed/stopped/ended, PR opened, deployment run, major decision. Append via `scripts/session-log.sh`. |
| `PLAN.md` | Strategy: goal, approach, milestones, risks | When the goal/approach/milestones/risks change — not per small step. |
| `SPEC.md` | Tactical design: problem, design, interfaces/contracts, out-of-scope | When the design or a contract is defined or changes. Per design-first doctrine, fill it *before* implementing. |
| `work/items/<id>.json` (this item) | `status`, `current_state`, `tickets`, append-only `history`, `roadmap`, `last_synced` (ADH-008 Phase 8 watermark) | **Seeded at session start** via `define-work-item.sh` (see below), then as work progresses — flip `status`, refresh `current_state`, append a `history` entry per significant action, update `roadmap`. `backlog.json`/`wip.json`/`archive.json` are generated views over this — never edit them directly. `last_synced` only moves at `#end_work_session`'s batched close-checkpoint, after every external write in the batch succeeds. |
| `work/backlog.json` | Groomed items not yet picked up (generated view — see above) | Regenerated automatically on every `work/items/*.json` write; never edit directly. |
| `work/scratchpad.json` | Ad-hoc / ticketless exploration | When doing ticketless investigation that isn't a full session. |
| `work/INBOX.md` | Raw unsorted capture | Immediately when something comes in ad-hoc — capture first, shape later. |
| `work/WORK_STATE.md` | Snapshot: counts, stale, blocked, next actions | Regenerate whenever `backlog.json`/`wip.json` change materially, and at pause/stop/end. |

## Session start ⇔ item store is mandatory and automated

**Every started session has a matching `in progress` item in
`work/items/<id>.json`, keyed by the session id — no exceptions.** This
linkage is not left to the agent to remember: `#initialize_work_session_folder`
(via `scripts/init-session.sh`) registers it automatically at session start,
through the one canonical constructor, `scripts/define-work-item.sh`:

- If the item file already exists (groomed via `#triage-inbox`/`#groom-item`),
  its fields are left untouched — only `status` flips to `in progress` and a
  `"session started"` `history` entry is appended (via
  `define-work-item.sh --record-event`). There is no physical "move" between
  files in this model — `status` is the one authoritative field, and
  `backlog.json`/`wip.json`/`archive.json` are **generated views** derived
  from it (`regenerate-views.sh`, run automatically after every write) —
  never hand-edited, never a second source of truth.
- Otherwise a **fresh** item is seeded from the session's
  goal/ticket/scope/task-type, with a `"session started"` `history` entry.
- Writes are serialized per-item via `define-work-item.sh`'s own file lock
  (`work/items/<id>.json.lock/`) — this is what makes the registration safe
  under real concurrent session-starts, not just idempotent in the
  read-modify-write sense the old `work/wip.json` model relied on (ADH-008
  Phase 1/7 — see below for why that distinction is load-bearing).
- `init-session.sh` refuses up front — before any side effect — if
  `work/items/` isn't populated yet but `backlog.json`/`wip.json` still hold
  real un-migrated content (`scripts/migrate-items-v2.sh` must run first).

**Do not "start" a session by any path that skips this.** A started session
must never leave `work/items/<id>.json` absent. If you ever find a live
session with no matching item file, reconcile it immediately by running
`scripts/define-work-item.sh <id> --status "in progress" ...` — the session
is not correctly tracked until you do.

**Why this replaced the old `work/wip.json` model (real incident, 2026-08-19):**
the old model's `lib/upsert_wip.py` had no locking — a plain read-modify-write
against one shared file. Under real concurrent session-starts, this dropped
entries via a lost-update race: two started sessions (`ADH-008-decouple-
control-exec` and `IO-234-block-bedrock-scp`) were found completely missing
from `work/wip.json` and `SESSIONS_STATE.md`, caught only by chance while
dry-running the migration tool, not by any check in the framework itself.
Both were restored from their own `CONTEXT.md` records before migrating. The
per-item file + lock model above is structurally immune to this — two
different items' writes never contend, and same-item writes serialize
through the lock instead of racing on a shared read-modify-write.

## Update discipline

- **Append-only, never rewrite history:** `CONTEXT.md`'s Activity log,
  `WORKLOG.md`, and each item's `history` array — only add, never edit or
  delete past entries. Use `scripts/session-log.sh <id> "<msg>" [--to worklog|context|both]`
  for the markdown logs so the timestamp/format stays consistent.
- **Keep-current (overwrite in place):** `CONTEXT.md` Current state, `TASKS.md`
  statuses, `PLAN.md`, `SPEC.md`, `work/WORK_STATE.md`. These reflect *now*,
  so replace stale content.
- **Rollup, not manual three-way agreement (ADH-008):** state flows one
  direction through defined sync points, not an obligation to keep three
  views in lockstep. `CONTEXT.md`'s Current state is the continuously
  updated, high-frequency narrative — update it live, as often as reality
  changes. `work/items/<id>.json`'s `status`/`current_state` only move at
  discrete lifecycle events (session start; `#end_work_session`'s
  close-checkpoint; an explicit `define-work-item.sh --status`/
  `--current-state` call) — never hand-edited, always through the
  constructor's own locked write path, which also regenerates
  `backlog.json`/`wip.json`/`archive.json`. `SESSIONS_STATE.md`'s `Status`
  column is set by the same lifecycle commands at those same points. Each
  hop has one writer; get the event recorded at its natural sync point and
  the rest follows — there is no separate "go reconcile the other two"
  step.
- **Cadence:** `TASKS.md` + `CONTEXT.md` Current state — continuously. Logs +
  the item's `history` — on each lifecycle sync point (not every `CONTEXT.md`
  edit). `PLAN.md`/`SPEC.md` — when the plan/design changes. `work/WORK_STATE.md`
  — on portfolio changes and at every lifecycle boundary.
- **Flush before you lose context:** before pausing, switching tasks, opening a
  PR, or when the conversation is about to be summarized, write the current
  state into `CONTEXT.md` + `TASKS.md` first so nothing is stranded in memory.
- **A flush is also a conversation boundary, not just a file write.** The
  point of flushing is that a *new* conversation can pick up from the files
  alone — so treat a flush as the moment to end the current conversation and
  continue in a fresh one, not just as a checkpoint inside an ever-growing
  one. This is what keeps a session's context (and cost) from growing
  unbounded across a pause/resume cycle. See `AGENTS.md` § Model & Context
  Discipline.

The lifecycle commands (`#pause_work_session`, `#resume_work_session`,
`#stop_work_session`, `#end_work_session`, `#sync-work`, `#define_deployment`,
etc.) enforce this at boundaries; this rule makes it a continuous obligation
in between.
