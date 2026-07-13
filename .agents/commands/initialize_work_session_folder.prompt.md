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

Session folder name = `<session-id>-<slug>` (or just `<session-id>` if it already reads as a slug).

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

This creates `<work-sessions-repo>/sessions/<session-id-slug>/` from
`session-template/`, fills in `CONTEXT.md`, registers a row in
`SESSIONS_STATE.md` (Status: `active`), **upserts the matching item in the
portfolio work tracker `work/wip.json`** (status `in progress` — see below),
creates the detached `worktrees/agentic-sdlc` worktree, and links a detached
tmux session `cw-<session-id>` (guarded — skipped if tmux isn't installed) —
all automatic, never gated on user input.

**Portfolio wip registration (automatic).** Starting a session must never
leave `work/wip.json` empty for that id — the script guarantees the
session-start ↔ portfolio-wip linkage:
- If `<session-id>` already exists in `work/backlog.json`, it is **moved** to
  `work/wip.json` (its groomed fields — title, description, tickets, roadmap —
  are preserved) and removed from the backlog.
- Otherwise a **fresh** wip entry is seeded from the session's
  goal/ticket/scope/task-type, following `work/template.json`'s shape.
- Either way `status` is set to `in progress`, `current_state` is set (blocked
  iff `--blockers` was given), and a `"session started"` entry is appended to
  the append-only `history`.
- The upsert is **idempotent** — an id already in `work/wip.json` is left
  untouched (no duplicate history, no clobbered progress) and other entries are
  never modified. It is skipped only if the target repo has no `work/` tracker
  at all.

Keep the three status views in agreement afterwards as work progresses:
`work/wip.json` `status` ⇔ `CONTEXT.md` Current state (`Blocked`) ⇔
`SESSIONS_STATE.md` `Status` (see `.agents/rules/session-state.instructions.md`).

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
- That the item was registered in `work/wip.json` (status `in progress`) —
  moved from `work/backlog.json` if it was groomed there, otherwise seeded from
  the session goal/ticket/scope/task-type
- That a session `.env` was written (defaults: `AWS_PROFILE=cw-test`,
  `AWS_DEFAULT_REGION=us-east-1`, `AWS_ALLOWED_PROFILES=cw-test,cw-partner`,
  `CLAUDE_CODE_DONT_INHERIT_ENV=true`) — loaded into the tmux env; edit it to
  change the profile, and run `#aws-reauth` if AWS creds need refreshing
- The agentic-sdlc tools worktree path (detached, on the default branch)
- That it was added to the VS Code workspace
- The tmux session name + the `tmux attach -t cw-<session-id>` command to enter it
- That target-repo worktrees are next, via `#create_work_tree.prompt.md` (if any target repos were named)
