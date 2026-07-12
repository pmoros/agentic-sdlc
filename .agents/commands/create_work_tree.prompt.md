---
agent: agent
description: Create a git worktree of a repo under repos/ for the active (or named) session. Atomic, script-backed — wraps scripts/create-worktree.sh. Use for "add a worktree for <repo>", "create a worktree for <ticket>", or as a step inside #start_work_session.
---

# Create Work Tree

Atomic, single-repo worktree creation. Wraps `scripts/create-worktree.sh`.
Reusable standalone (e.g. "add another target repo mid-session") or as a step
called by the `start-work-session` skill.

Per the **Reference Repo Policy** in `AGENTS.md`: repos under
`repos/` are read-only sources of truth — always on their default
branch, always kept in sync, never edited directly. This command is the only
way work gets a place to happen; there is no branch-only/no-worktree mode.

## Steps

### 1. Identify the session

If a session was already established earlier in the conversation, use it.
Otherwise read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling
`../work-sessions` of this repo) and filter rows with
`Status: active`:
- Exactly one → use it.
- Multiple → list them and ask which session this worktree belongs to.
- None → tell the user to run `#initialize_work_session_folder.prompt.md` or the `start-work-session` skill first, and stop.

### 2. Identify the repo, branch, and base ref

Ask only for what isn't already known from context:
- **Repo** — a name (resolved to `repos/<name>`, sibling of this repo) or an explicit path.
- **Branch name** — required unless this is the special agentic-sdlc tools worktree (which uses `--detach`, handled by `initialize_work_session_folder` instead — this command is for target repos).
- **Base ref** — default: the repo's auto-detected default branch. Offer the user a chance to override (e.g. the `code` monorepo conventionally branches off `develop`, not its default branch).

### 3. Run the script

Compute the destination: `<work-sessions-repo>/sessions/<session-name>/worktrees/<repo-name>-<branch-slug>`.

Describe the action, then run (autonomous — `git worktree add` is autonomous per the Git Policy table in `AGENTS.md`, describe before running rather than requesting approval):

```bash
scripts/create-worktree.sh <repo-path> --dest <dest> --branch <branch> --base <base>
```

If the repo is a Node project needing a specific dependency strategy other than the default `--deps auto`, ask which (`clone | install | link | none`) — see `docs/create-worktree.md` for the decision matrix; otherwise omit `--deps` and let `auto` decide.

### 4. Add the worktree to the VS Code workspace

Open `<work-sessions-repo>/work-sessions.code-workspace` (the
single, tracked workspace file for that repo). Add a new entry to its
`folders` array:
- If a `// ── Session worktrees ──` comment already exists, append the entry immediately after it.
- Otherwise, append the entry before the closing `]` of `folders`, preceded by that comment.

```jsonc
{
  "name": "<session-name> — <repo-name> worktree",
  "path": "sessions/<session-name>/worktrees/<repo-name>-<branch-slug>"
}
```

Autonomous — no approval needed, this is part of worktree creation bookkeeping.

### 5. Report

Tell the user:
- The worktree path and branch/base ref used
- That it was added to the VS Code workspace
- A reminder that the source repo at `<repo-path>` stays read-only — all work happens in the new worktree
- If `--deps` produced a warning (e.g. incomplete CoW clone, lockfile drift), surface it verbatim
