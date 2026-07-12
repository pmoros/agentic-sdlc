# Stop Work Session

You are stopping an active work session. This saves state, optionally commits
work, and removes target-repo worktrees. Branches are always retained
locally. The session's `worktrees/agentic-sdlc` worktree is left in place —
tools may still be needed right up until the session folder itself is
archived or deleted (see `#end_work_session.prompt.md`).

## Steps

### 1. Identify the active session

Read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo) and filter rows with `Status: active`.

- If exactly one is found, use it.
- If multiple are found, list them (session ID + title) and ask which to stop.
- If none are found, inform the user and stop.

### 2. Ask status questions

Ask the user each of the following in sequence. Do not skip.

1. **What was accomplished?** — brief bullet list of work done since last start/resume
2. **What was NOT completed?** — what remains unfinished that was in scope
3. **Reason for stopping** — choose one: `context-switching | blocked | abandoned | replaced`
4. **Permanently abandoned or just postponed?** — `abandoned | postponed`
5. **Open blockers or notes for next time** — (press Enter for none)

### 3. Update session files

Update `<work-sessions-repo>/sessions/<session-id>/CONTEXT.md`:
- Set `- **Blocked:**` to `yes` if question 5 has content, else `no`.
- Set `- **Description:**` to `<abandoned|postponed> (<reason>) — <question 5 answer or "none">`.
- Append to `## Activity log`:
  ```
  - <YYYY-MM-DD HH:MM> session stopped (<reason>) — <one-line summary of accomplished work>
  ```

Update `<work-sessions-repo>/sessions/<session-id>/TASKS.md`: for remaining/unfinished items from question 2, add or update rows with status `blocked` or `todo` and a Notes entry `[remaining at stop]`.

Append to `<work-sessions-repo>/sessions/<session-id>/WORKLOG.md`:
```
- <YYYY-MM-DD HH:MM> session stopped (<reason>) — <one-line summary>
```

Also update `<work-sessions-repo>/SESSIONS_STATE.md`: find the row for this session and set **Status** to `stopped` and **Last Change** to today.

These file writes are autonomous.

### 4. Commit work

List the session's target-repo worktrees: `ls <work-sessions-repo>/sessions/<session-id>/worktrees/` excluding `agentic-sdlc`. For each, run `git -C <worktree-path> status` and show the summary. Ask:
> "Which files in `{worktree-path}` should be staged? (all / specific paths / none — press Enter to skip)"

If committing:
- Stage as directed
- Propose a Conventional Commits message based on what was accomplished
- Show the full proposed commit command and **wait for explicit approval before running `git commit`**

### 5. Remove target-repo worktrees

For each target-repo worktree from step 4 (never `agentic-sdlc` — see the note above):

Show the following and **wait for explicit approval before running** (worktree removal is autonomous per the Git Policy table in `AGENTS.md` in the sense that it needs no separate write-operation protocol, but still describe it first since it deletes a working directory):
> This will remove the working directory at `<work-sessions-repo>/sessions/<session-id>/worktrees/{name}`. Branch `{branch-name}` is retained in `{repo-path}`.
```bash
git -C {repo-path} worktree remove {worktree-path}
```

After each worktree is removed, autonomously edit `<work-sessions-repo>/work-sessions.code-workspace` and remove the `folders` entry whose `"path"` matches `sessions/<session-id>/worktrees/{name}`. If no matching entry exists, skip silently. No separate approval needed — this is part of worktree cleanup.

### 6. Kill the tmux session

Tear down the session's tmux session (guarded — no-op if tmux is absent):

```bash
scripts/session-tmux.sh kill <session-id>
```

### 7. Confirm

Tell the user:
- What was committed and/or removed
- Branches retained (list them with their source repo path)
- Session state saved at `<work-sessions-repo>/sessions/<session-id>/`
- The `worktrees/agentic-sdlc` worktree is still there for tool access
- tmux session `cw-<session-id>` killed
- Resume later with `#resume_work_session.prompt.md` (re-creates the tmux session)
