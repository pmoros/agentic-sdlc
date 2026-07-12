# End Work Session

You are closing out a completed work session. This command handles session
closure only — committing, pushing, and opening a PR are separate commands
(`#sync-work.prompt.md` and `#open-pr.prompt.md`).

Follow each step carefully. Do not skip questions or combine steps.

## Steps

### 1. Identify the session

Read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo). If multiple sessions have `Status: active` or `paused`, list them and ask which to end. Read `<work-sessions-repo>/sessions/<session-id>/CONTEXT.md` and `TASKS.md` for all subsequent steps.

### 2. Ask closing questions

Ask the user each of the following in sequence. Do not skip.

1. **Summary of accomplishments** — what was delivered in this session? (be specific)
2. **ADRs or decisions documented?** — list them by title/file under `adrs/`, or enter `none`
3. **Task review** — show the current `TASKS.md` table. For any item not `done`, ask: "Skip (out of scope) or carry over to a new session?"
4. **Follow-up tasks** — any tasks that emerged but are out of scope for this session? (create new sessions for them later)

### 3. Check git state

List the session's target-repo worktrees: `ls <work-sessions-repo>/sessions/<session-id>/worktrees/` excluding `agentic-sdlc`. For each, determine its branch and verify it has been pushed and a PR exists. If either is missing, display:

> ⚠ **Before closing:** It looks like `#sync-work.prompt.md` and/or `#open-pr.prompt.md` have not been run for `{repo-name}`.
> - Branch pushed? [yes / no]
> - PR open? [yes / no]
>
> You can proceed without these, but work on this branch may not be visible to your team. Continue anyway? (yes / no)

Do not block session closure if the user chooses to continue.

### 4. Update session files

Update `<work-sessions-repo>/sessions/<session-id>/CONTEXT.md`:
- Set `- **Description:**` to `ended — <summary from question 1>`.
- Append to `## Activity log`:
  ```
  - <YYYY-MM-DD HH:MM> session ended — <one-line summary>
  ```

Update `<work-sessions-repo>/sessions/<session-id>/TASKS.md`: mark items per question 3's answers (`done` or a Notes entry `[out of scope]`).

Append to `<work-sessions-repo>/sessions/<session-id>/WORKLOG.md`:
```
- <YYYY-MM-DD HH:MM> session ended — <summary from question 1>
```

If question 4 named follow-up tasks, note them in the same entry under a `Follow-ups:` line — they become the seed for a future `#initialize_work_session_folder.prompt.md` run, not automatic new sessions.

Also update `<work-sessions-repo>/SESSIONS_STATE.md`: find the row for this session and set **Status** to `done` and **Last Change** to today.

All file writes are autonomous.

### 5. Remove all worktrees

For each target-repo worktree from step 3, show the following and **wait for explicit approval before running**:
> This will remove the working directory at `<work-sessions-repo>/sessions/<session-id>/worktrees/{name}`. The branch is retained in `{repo-path}`.
```bash
git -C {repo-path} worktree remove {worktree-path}
```

The `worktrees/agentic-sdlc` worktree is removed too at this point, since the session is fully closing:
```bash
git -C <agentic-sdlc-repo-path> worktree remove <work-sessions-repo>/sessions/<session-id>/worktrees/agentic-sdlc
```

After each worktree is removed, autonomously edit `<work-sessions-repo>/work-sessions.code-workspace` and remove the `folders` entry whose `"path"` matches `sessions/<session-id>/worktrees/{name}` (including the `agentic-sdlc` entry). If no matching entry exists, skip silently. No separate approval needed — this is part of worktree cleanup.

### 5b. Kill the tmux session

Tear down the session's tmux session (guarded — no-op if tmux is absent):

```bash
scripts/session-tmux.sh kill <session-id>
```

### 6. Confirm

Tell the user:
- Session folder stays at `<work-sessions-repo>/sessions/<session-id>/` (it's committed to the work-sessions repo, nothing to archive or delete — the whole point of that repo is that it survives)
- Worktrees removed (list each); branches retained in their source repos
- VS Code workspace updated; tmux session `cw-<session-id>` killed
- Follow-up tasks noted (list them)
- Suggest next step: `#find-session.prompt.md` to review other open sessions, or the `start-work-session` skill for a follow-up task
