# 0002 — Per-Session Isolation of `work-sessions` State

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-18 |
| **Deciders** | Paul Moros |
| **Tags** | work-sessions, concurrency, git-worktree, session-state, data-integrity |

## Context

`work-sessions` is the sibling repo that holds all session state — the registry
(`SESSIONS_STATE.md`), the portfolio trackers (`work/wip.json`,
`work/backlog.json`), and one folder per session under `sessions/<id>/`
(`CONTEXT.md`, `TASKS.md`, `WORKLOG.md`, worktrees, …). It is a **single git
checkout**, and today every concurrent session/agent shares that one working
tree and commits into it.

Two facts about the current mechanics (confirmed by reading `scripts/` and the
lifecycle prompts):

1. **The framework never commits `work-sessions` onto a defined branch.**
   `init-session.sh` and `session-log.sh` *write* files (registry rows, the
   session folder, wip entries) but run no `git` at all. `#sync-work` — the only
   commit/push command — operates exclusively on **target-repo** worktrees and
   *explicitly excludes* the state repo (`agentic-sdlc` and, by extension, the
   `work-sessions` checkout itself). So whether and where session state gets
   committed is left to whatever the agent does ad hoc, on **whatever branch the
   shared checkout happens to be on** at that moment.

2. **Three shared files are mutated by every session concurrently:**
   `SESSIONS_STATE.md`, `work/wip.json`, and the (gitignored, therefore
   harmless) `.code-workspace`. Everything else a session writes lives under its
   own disjoint `sessions/<id>/` path.

This failure is not hypothetical — it has been observed in practice. A session's
registration commit is made on whatever branch is checked out; another agent then
switches or merges that shared checkout to a different branch. The first session's
commit is left on **no branch at all** (reachable only via reflog,
garbage-collection-eligible) and its files vanish from the working tree — the
mainline ends up with zero trace of the session. The same class of race also
explains why the registry drifts, missing rows for genuinely-active sessions.

Root cause: **a single shared checkout + hand-edited shared files + no per-session
commit target.** Any fix must let concurrent sessions persist their state
without (a) switching a branch out from under another agent, or (b) contending
on the same lines of the same shared files.

## Decision

Adopt **per-session isolation** of `work-sessions` state, built from three
coupled parts. The parts are coupled deliberately: per-session branches *alone*
make the problem worse, because committing a session branch from the single
shared checkout forces the very `git checkout` that strands another session's
in-flight commit. Branches are only safe when paired with per-session worktrees **and** a
guarantee that session commits never touch shared files.

### Part 1 — One `work-sessions` worktree per session, on `session/<id>`

At session start, alongside the session folder, create a dedicated git worktree
of `work-sessions` itself, on a per-session branch:

```bash
git -C <work-sessions> worktree add ../work-sessions.worktrees/<id> -b session/<id> origin/main
```

The worktree is a **sibling** (`work-sessions.worktrees/<id>/`), never nested
under `sessions/<id>/worktrees/` — a worktree of a repo cannot live inside that
repo's own tracked tree. (The `<repo>.worktrees/` sibling convention already
exists in this tree, e.g. `auth-app.worktrees/`.) The agent performs **all**
session-state writes and commits in its own worktree, on its own branch, so no
other session can ever switch or reset it. This directly removes the
"branch yanked out from under me" failure mode.

### Part 2 — One per-session source of truth; the aggregate is generated

The status of a session is tracked today across **three** hand-synced shared
files (`SESSIONS_STATE.md` ⇔ `CONTEXT.md` "Current state" ⇔ `work/wip.json`
status). That triple-write is both the concurrency contention *and* a standing
maintenance burden. Collapse it to one:

- **Source of truth:** `sessions/<id>/state.json` — machine-readable
  (`status`, `title`, `tickets[]`, `created`, `last_change`, `blockers`,
  `task_type`, `scope`). Owned solely by that session → disjoint path → **never
  conflicts** across branches. `CONTEXT.md` remains human narrative only.
- **`SESSIONS_STATE.md` and `work/wip.json` become generated views**, rebuilt by
  a new idempotent `scripts/regenerate-sessions-state.sh` that scans
  `sessions/*/state.json`. Both carry a `GENERATED — do not edit` header.
- `work/backlog.json` stays a portfolio file, single-writer via the
  project-manager flow on `main`.

The invariant this buys: **a `session/<id>` branch only ever touches
`sessions/<id>/**`.** Nothing shared. Therefore session branches merge in any
order with no conflicts, ever.

### Part 3 — Auto-merge + regenerate integration; `main` is single-writer

Because session branches are path-disjoint:

- A session pushes `session/<id>` to origin on sync / pause / stop / end.
- A single **`sync-sessions-state`** step (a script, or a project-manager task)
  merges the `session/*` branches into `main` — conflict-free by construction —
  and then runs `regenerate-sessions-state.sh` to refresh the aggregate. This is
  the **only** writer of the shared aggregate, so it never races anyone.
- **Hard rule (recorded in `AGENTS.md`): agents never run `git checkout` /
  `git switch` in the canonical `work-sessions` checkout.** It stays on `main`,
  single-writer. All session mutation happens in per-session worktrees.

### Lifecycle command changes

| Command | Change |
|---|---|
| `init-session.sh` | Create the `session/<id>` worktree + branch; write `state.json`; **stop** line-editing `SESSIONS_STATE.md` / `wip.json` (regenerate instead). |
| `#sync-work` | Also commit + push the session's `work-sessions` worktree (`session/<id>`), not only target-repo worktrees. |
| `#resume_work_session` | Recreate / refresh the per-session worktree from `origin/session/<id>`. |
| `#pause` / `#stop` / `#end` | Commit + push `session/<id>`; remove the per-session worktree; trigger the aggregate regenerate on `main`. |
| **new** `regenerate-sessions-state.sh` | Scan `sessions/*/state.json` → rebuild `SESSIONS_STATE.md` + `work/wip.json`. Idempotent; unit-tested against a minimal fixture. |

### Migration

1. Add `state.json` to `session-template/`; backfill one per existing session
   from current `SESSIONS_STATE.md` rows.
2. Convert `SESSIONS_STATE.md` / `work/wip.json` to generated (mark them; add the
   script) and reconcile `main` so it lists every currently-active session.
3. Recover any records already orphaned by this bug by merging their
   `sessions/<id>/` folders into the mainline.
4. Add the "never checkout in `work-sessions`" rule to `AGENTS.md` and update the
   lifecycle prompts.

## Consequences

### Positive

- **Eliminates the orphaned-commit / lost-state failure class.** No session ever
  shares a branch or a working tree with another, so nobody's commit can be
  stranded off-branch by someone else's checkout.
- **Session branches are conflict-free by construction** — they only touch their
  own `sessions/<id>/` subtree, so `main` integration never hits a merge
  conflict regardless of ordering or concurrency.
- **Collapses the three-way status sync into one file**, removing both the
  contention and a perennial "keep the three views in agreement" maintenance
  rule. `SESSIONS_STATE.md` and `wip.json` stop drifting because they are
  derived, not hand-maintained.
- **Mirrors the existing target-repo worktree model**, reusing
  `create-worktree.sh` mechanics and mental model rather than inventing a new
  one.

### Negative / Trade-offs

- **More git objects and paths per session** — an extra worktree and branch per
  session, plus a `work-sessions.worktrees/` sibling tree to manage and clean
  up. Cheap in bytes (state is text, no `node_modules`), but more lifecycle
  bookkeeping to get right (creation on init, removal on end, refresh on resume).
- **`main` becomes eventually-consistent**, not immediately-consistent — a
  session's state is authoritative on its own branch until the
  `sync-sessions-state` step runs. Anything that reads `SESSIONS_STATE.md`
  expecting live truth must instead read `state.json` (or accept lag). The
  project-manager flows that scan the registry need auditing for this.
- **Real implementation surface**: `init-session.sh`, four lifecycle prompts, a
  new generator script + tests, `AGENTS.md`, and a one-time migration — sequenced
  in phases. A partial rollout (e.g. worktrees without the derived
  registry) would reintroduce shared-file conflicts, so the phases must land in
  order.

### Neutral

- The `.code-workspace` file is already gitignored, so it never participated in
  the conflict and needs no change beyond the existing per-session add/remove
  bookkeeping.
- `work/backlog.json` is unaffected: it remains a portfolio-level, single-writer
  file owned by the project-manager flow on `main`.

## Alternatives Considered

**A — Serialize commits to `main` with a repo lock (no branches).** Every session
takes a lock, `pull --rebase`, commits to `main`, releases. Rejected: still one
shared checkout and shared files, so it trades orphaning for lock contention and
rebase conflicts on `SESSIONS_STATE.md`/`wip.json`; it also serializes all
sessions' state writes behind a single lock.

**B — Per-session branches in the *shared* checkout (no per-session worktree).**
Rejected outright: this is the configuration that caused the incident. Committing
a session branch requires `git checkout` on the shared tree, which strands any
other session's in-flight branch. Branches without worktrees make the problem
worse, not better.

**C — Plumbing-only writes (`git commit-tree` / `GIT_INDEX_FILE`) to update a
`session/<id>` ref without a checkout.** Rejected: technically avoids the extra
worktree, but it is fragile, hard to reason about, and alien to the rest of the
framework's worktree-based model — a maintenance and debuggability cost far
above the price of one cheap text-only worktree.

**D — Keep hand-edited shared files but shard nothing.** Rejected: leaves the
`SESSIONS_STATE.md` / `wip.json` contention in place, so even with per-session
worktrees, merging session branches back would conflict on every shared line.
