---
agent: agent
description: Create the session folder for a new piece of work in work-sessions, register it, and set up its mandatory agentic-sdlc tools worktree. Atomic, script-backed — wraps scripts/init-session.sh. Called by #start_work_session as its first step; can also be run standalone.
---

# Initialize Work Session Folder

Atomic session-folder setup. Wraps `scripts/init-session.sh`. Does **not**
create target-repo worktrees — use `#create_work_tree.prompt.md` for each
target repo after this completes (the `start-work-session` skill wires both
together).

## Steps

### 1. Gather session details

If these were already collected earlier in the conversation (e.g. by the
`start-work-session` skill), use them directly. Otherwise ask in sequence:

1. **Task type** — `feat | fix | chore | refactor | docs | spike`
2. **Ticket / issue ID** — paste an existing ID/URL, or press Enter to skip
3. **Short description** — slug format: lowercase, hyphens only, max 4 words
4. **One-line goal** — full sentence describing what this session will accomplish
5. **Scope estimate** — `XS | S | M | L | XL`
6. **Known dependencies or blockers** — press Enter for none

### 2. Identify target repos

Ask (unless already known):
> "Which repos under `repos/` will this session touch, if any? List names or press Enter for tools-only." 

Record the list — this command doesn't act on it, but the caller
(`start-work-session`) uses it to call `#create_work_tree.prompt.md` once per
repo right after this step.

### 3. Determine the Session ID

- **Ticket provided:** extract the key (e.g. `PROJ-6025` from `https://yourcompany.atlassian.net/browse/PROJ-6025`).
- **No ticket:** read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions`), find the highest existing `ADH-NNN`, increment by 1 (`ADH-001` if none exist).
- **Reopening an item (ADH-011)**: if the caller (typically the
  `start-work-session` skill, after its own reopen check) passes
  `--reopen-item <item-id>` instead of gathering a fresh id, skip the two
  bullets above entirely — the actual session id is computed by
  `init-session.sh` itself from the item's existing `sessions[]`
  (`<item-id>--eN`), not by this step.

Session folder name = `<session-id>-<slug>` (or just `<session-id>` if it already reads as a slug) — **except on a reopen**, where the folder name is whatever `init-session.sh` derives (`<item-id>--eN`).

### 4. Run the script

Describe the action, then run (session file read/write and worktree add are
both autonomous per the Git Policy table in `AGENTS.md` — describe before
running rather than requesting approval):

```bash
scripts/init-session.sh <session-id-slug> \
  --goal "<goal>" \
  --ticket "<ticket-url-or-id>" \
  --scope <XS|S|M|L|XL> \
  --task-type <type> \
  --blockers "<blockers or omit>"
```

**On a reopen**, run instead (no positional session-id-slug — the script
computes it):

```bash
scripts/init-session.sh --reopen-item <item-id> --goal "<goal>"
```

This creates `<work-sessions-repo>/sessions/<session-id-slug>/` from
`session-template/`, fills in `CONTEXT.md`, registers a row in
`SESSIONS_STATE.md` (Status: `active`), **registers the matching item in
`work/items/<session-id>.json`** (status `in progress` — see below), creates
the detached `worktrees/agentic-sdlc` worktree, and links a detached tmux
session `cw-<session-id>` (guarded — skipped if tmux isn't installed) — all
automatic, never gated on user input.

**Item registration (automatic).** Starting a session must never leave
`work/items/<session-id>.json` absent — the script guarantees the
session-start ↔ item linkage, through the one canonical constructor,
`scripts/define-work-item.sh`:
- If the item file already exists (groomed via `#triage-inbox`/`#groom-item`),
  its fields — title, description, tickets, roadmap — are left untouched;
  only `status` flips to `in progress`.
- Otherwise a **fresh** item is seeded from the session's
  goal/ticket/scope/task-type.
- **On `--reopen-item` (ADH-011)**: neither of the above — the item must
  already exist (fails loudly if not), and instead of a plain status flip
  the script calls `--open-episode`, which appends a new `sessions[]` entry
  and records its own history event. No fresh item is ever seeded this way.
- Either way `current_state` is set (blocked iff `--blockers` was given), and
  a `"session started"` entry is appended to the append-only `history` — via
  `define-work-item.sh --record-event`, not a hand edit.
- Writes are serialized per-item through the constructor's own file lock —
  safe under real concurrent session-starts (ADH-008 Phase 1/7; a lost-update
  race in the old `work/wip.json` model actually dropped this session's own
  registration once, see `.agents/rules/session-state.instructions.md`).
- Refuses up front — before any side effect — if `work/items/` isn't
  populated yet but `backlog.json`/`wip.json` still hold real un-migrated
  content (`scripts/migrate-items-v2.sh` must run first).
- `backlog.json`/`wip.json`/`archive.json` are **generated views**, rebuilt
  automatically after every `work/items/*.json` write — never hand-edited.

State moves through the rollup chain afterwards as work progresses, not a
"keep three views in agreement" obligation: `CONTEXT.md` Current state is the
continuously-updated narrative; `work/items/<id>.json` and
`SESSIONS_STATE.md`'s `Status` only move at defined lifecycle sync points
(see `.agents/rules/session-state.instructions.md`).

### 5. Add the worktree to the VS Code workspace

Open `<work-sessions-repo>/work-sessions.code-workspace` — the
single, tracked workspace file for that repo (no ambiguity to resolve; unlike
the old per-repo scheme, there is exactly one file). Add a new entry to its
`folders` array:
- If a `// ── Session worktrees ──` comment already exists, append the entry immediately after it.
- Otherwise, append the entry before the closing `]` of `folders`, preceded by that comment.

```jsonc
{
  "name": "<session-id> — agentic-sdlc tools",
  "path": "sessions/<session-id-slug>/worktrees/agentic-sdlc"
}
```

Autonomous — no approval needed, this is part of worktree creation bookkeeping.

### 6. Report

Tell the user:
- The session folder path
- That the item was registered in `work/items/<session-id>.json` (status
  `in progress`) — reshaped in place if it was already groomed, otherwise
  seeded from the session goal/ticket/scope/task-type
- That a session `.env` was written (defaults: `AWS_PROFILE=cw-test`,
  `AWS_DEFAULT_REGION=us-east-1`, `AWS_ALLOWED_PROFILES=cw-test,cw-partner`,
  `CLAUDE_CODE_DONT_INHERIT_ENV=true`) — loaded into the tmux env; edit it to
  change the profile, and run `#aws-reauth` if AWS creds need refreshing
- The agentic-sdlc tools worktree path (detached, on the default branch)
- That it was added to the VS Code workspace
- The tmux session name + the `tmux attach -t cw-<session-id>` command to enter it
- That target-repo worktrees are next, via `#create_work_tree.prompt.md` (if any target repos were named)
