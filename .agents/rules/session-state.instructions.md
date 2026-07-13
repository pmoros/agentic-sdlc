# Session State Maintenance

While a session is active, its tracking files are **living documents** — keep
them current *as you work*, not only at lifecycle boundaries (start / pause /
stop / end). If the session were resumed cold from these files alone, they
should fully explain where things stand. All these writes are **autonomous**
— no approval needed (per the Git Policy in `AGENTS.md`: session file
read/write is autonomous).

**Identify the active session** from `work-sessions/SESSIONS_STATE.md`
(the `Status: active` row) or from the session worktree you're operating in.
State lives in two places:

- **Portfolio-level** — `work-sessions/work/`: `backlog.json`,
  `wip.json`, `scratchpad.json`, `INBOX.md`, `WORK_STATE.md`.
- **This session** — `work-sessions/sessions/<id>/`: `CONTEXT.md`,
  `PLAN.md`, `SPEC.md`, `TASKS.md`, `WORKLOG.md`.

## What each file holds, and when to update it

| File | Holds | Update it when… |
|---|---|---|
| `TASKS.md` | Granular task table (Task / Status `todo\|in progress\|blocked\|done` / Owner / Notes) | **Continuously** — the moment a task is picked up, finished, blocked, or discovered. This is the highest-frequency file. |
| `CONTEXT.md` → *Current state* | One or two lines: where things stand right now + `Blocked: yes/no` | Whenever reality changes — blocked/unblocked, waiting on review, direction shifts. Keep it true *now*. |
| `CONTEXT.md` → *Activity log* | Append-only terse timestamped actions | On every significant action (branch/worktree/PR created, decision made, blocker hit). Append via `scripts/session-log.sh`. |
| `CONTEXT.md` → *Tickets / contacts / dates* | Live reference | When a ticket/contact/date is learned or changes. |
| `WORKLOG.md` | Append-only log of lifetime events | Session started/paused/resumed/stopped/ended, PR opened, deployment run, major decision. Append via `scripts/session-log.sh`. |
| `PLAN.md` | Strategy: goal, approach, milestones, risks | When the goal/approach/milestones/risks change — not per small step. |
| `SPEC.md` | Tactical design: problem, design, interfaces/contracts, out-of-scope | When the design or a contract is defined or changes. Per design-first doctrine, fill it *before* implementing. |
| `work/wip.json` (this item) | `status`, `current_state`, `work_items` (PR/links), append-only `history`, `roadmap` | **Seeded at session start** (see below), then as work progresses — flip `status`, refresh `current_state`, append a `history` entry per significant action, add PR/artifact links, update `roadmap`. |
| `work/backlog.json` | Groomed items not yet picked up | When new work is discovered/groomed, or an item moves to WIP / done. |
| `work/scratchpad.json` | Ad-hoc / ticketless exploration | When doing ticketless investigation that isn't a full session. |
| `work/INBOX.md` | Raw unsorted capture | Immediately when something comes in ad-hoc — capture first, shape later. |
| `work/WORK_STATE.md` | Snapshot: counts, stale, blocked, next actions | Regenerate whenever `backlog.json`/`wip.json` change materially, and at pause/stop/end. |

## Session start ⇔ portfolio wip is mandatory and automated

**Every started session has a matching `in progress` item in `work/wip.json`,
keyed by the session id — no exceptions.** This linkage is not left to the
agent to remember: `#initialize_work_session_folder` (via
`scripts/init-session.sh`) **upserts** it automatically at session start:

- If the id already exists in `work/backlog.json`, it is **moved** to
  `work/wip.json` (groomed fields preserved) and removed from the backlog —
  this is the automated form of the README's "move the item backlog→wip before
  starting a session" step.
- Otherwise a **fresh** wip entry is seeded from the session's
  goal/ticket/scope/task-type, following `work/template.json`'s shape, with a
  `"session started"` `history` entry.
- The upsert is idempotent and never clobbers other entries.

**Do not "start" a session by any path that skips this.** A started session
must never leave `work/backlog.json` / `work/wip.json` as empty `{}`
placeholders for that id. If you ever find a live session with no `work/wip.json`
entry (e.g. one created before this was automated), reconcile it immediately by
adding the entry — the session is not correctly tracked until you do.

## Update discipline

- **Append-only, never rewrite history:** `CONTEXT.md`'s Activity log,
  `WORKLOG.md`, and each item's `history` array — only add, never edit or
  delete past entries. Use `scripts/session-log.sh <id> "<msg>" [--to worklog|context|both]`
  for the markdown logs so the timestamp/format stays consistent.
- **Keep-current (overwrite in place):** `CONTEXT.md` Current state, `TASKS.md`
  statuses, `PLAN.md`, `SPEC.md`, `work/WORK_STATE.md`, and `wip.json`'s
  `status`/`current_state`. These reflect *now*, so replace stale content.
- **Keep the three status views in agreement:** `wip.json` `status` ⇔
  `CONTEXT.md` Current state (`Blocked`) ⇔ `SESSIONS_STATE.md` `Status`. If one
  changes, reconcile the others.
- **Cadence:** `TASKS.md` + `CONTEXT.md` Current state — continuously. Logs +
  `wip.json` history — on each significant event. `PLAN.md`/`SPEC.md` — when the
  plan/design changes. `work/*.json` + `WORK_STATE.md` — on portfolio changes
  and at every lifecycle boundary.
- **Flush before you lose context:** before pausing, switching tasks, opening a
  PR, or when the conversation is about to be summarized, write the current
  state into `CONTEXT.md` + `TASKS.md` first so nothing is stranded in memory.

The lifecycle commands (`#pause_work_session`, `#resume_work_session`,
`#stop_work_session`, `#end_work_session`, `#sync-work`, `#define_deployment`,
etc.) enforce this at boundaries; this rule makes it a continuous obligation
in between.
