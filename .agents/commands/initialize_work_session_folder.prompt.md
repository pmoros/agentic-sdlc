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
`SESSIONS_STATE.md` (Status: `active`), creates the detached
`worktrees/agentic-sdlc` worktree, and links a detached tmux session
`cw-<session-id>` (guarded — skipped if tmux isn't installed) — all automatic,
never gated on user input.

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
- That a session `.env` was written (defaults: `AWS_PROFILE=cw-test`,
  `AWS_DEFAULT_REGION=us-east-1`, `AWS_ALLOWED_PROFILES=cw-test,cw-partner`,
  `CLAUDE_CODE_DONT_INHERIT_ENV=true`) — loaded into the tmux env; edit it to
  change the profile, and run `#aws-reauth` if AWS creds need refreshing
- The agentic-sdlc tools worktree path (detached, on the default branch)
- That it was added to the VS Code workspace
- The tmux session name + the `tmux attach -t cw-<session-id>` command to enter it
- That target-repo worktrees are next, via `#create_work_tree.prompt.md` (if any target repos were named)
