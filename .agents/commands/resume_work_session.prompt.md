# Resume Work Session

You are resuming a previously paused or stopped work session. Follow these steps in order.

## Steps

### 1. List available sessions

Read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo) — it is the authoritative index. Filter rows whose **Status** is `paused` or `stopped`.

- If none are found, inform the user there are no sessions to resume and stop.
- If exactly one is found, display its summary and ask the user to confirm before proceeding.
- If multiple are found, display a table and ask which to resume:

```
#  Session                          Status   Title
1  PROJ-123-oauth-refresh           paused   Implement OAuth token refresh
2  ADH-004-login-race-condition     stopped  Fix token refresh race condition
```

### 2. Display session summary

Read `<work-sessions-repo>/sessions/<session-id>/CONTEXT.md` and `TASKS.md`. Show:
- **Overview**, **Tickets**, **Current state** (Blocked + Description)
- **Tasks** from `TASKS.md` (current status column)
- Last entry in `## Activity log`

### 3. Ask orientation questions

Ask the user:

1. **Has anything changed since you paused?** — new requirements, resolved blockers, scope changes? (press Enter if nothing changed)
2. **Is the goal still accurate?** — show the current Overview line, ask to confirm or update

**Wait for both answers before proceeding.** Then:

- Update `CONTEXT.md` with any changes (Overview, Current state).
- For each ticket in the Tickets table (or blocker mentioned in Current state) that references a Jira key (e.g. `CHG-47249`, `PROJ-6559`): call the discovered Jira MCP tool to check its current status. If it's now resolved/approved, surface it prominently:
  > ✅ `{TICKET-KEY}` is now **{status}** — blocker cleared, ready to proceed.

Append to `## Activity log`:
```
- <YYYY-MM-DD HH:MM> session resumed — <any context changes noted>
```

### 4. Refresh the agentic-sdlc tools worktree

Always run this, unconditionally — it's what keeps the session's tools current:

```bash
scripts/create-worktree.sh --refresh <work-sessions-repo>/sessions/<session-id>/worktrees/agentic-sdlc
```

Report the resulting commit (script prints it) — if it advanced, note that agentic-sdlc's tools/commands/runbooks may have changed since the session started.

### 4b. Ensure the tmux session

Re-create the session's tmux session if it's gone (e.g. after a reboot), then print the attach hint:

```bash
scripts/session-tmux.sh ensure <session-id> <work-sessions-repo>/sessions/<session-id>
```

(Guarded — a no-op if tmux isn't installed. Never run `tmux attach` yourself; the script prints the `tmux attach -t cw-<session-id>` line for the user to run.)

### 5. Check for PR review threads

Before any GitHub operation, load `.agents/rules/github.instructions.md` to confirm MCP tool priority.

List the session's target-repo worktrees: `ls <work-sessions-repo>/sessions/<session-id>/worktrees/` excluding `agentic-sdlc`. For each, determine its branch with `git -C <worktree-path> rev-parse --abbrev-ref HEAD`, then:
1. Call `mcp__github__list_pull_requests` with `head: "{org}:{branch}"` to find the PR number.
2. If a PR exists, call `mcp__github__pull_request_read` with `method: "get_review_comments"` to get threads.
3. Count threads where `isResolved: false`.

- If unresolved threads > 0:
  > ⚠ `{repo-name}` PR has **N** unresolved review threads. Run `#review-pr.prompt.md` to triage them.
- If all resolved (or no threads):
  > ✓ `{repo-name}` PR has no unresolved review threads.
- If no open PR exists for the branch: note it — no review check needed yet.
- If the MCP tool fails: report the error and the parameters used — **do not skip silently**.

### 6. Verify target-repo worktrees are present

For each target-repo worktree from step 5, check whether the directory still exists:
- If it exists: confirm to the user it is ready.
- If it is missing (was removed): offer to recreate it on the existing branch. Show and **wait for explicit approval before running**:

```bash
scripts/create-worktree.sh <repo-path> --dest <work-sessions-repo>/sessions/<session-id>/worktrees/<repo>-<slug> --branch <existing-branch-name>
```

(The script adopts the existing branch since it already exists — no `--base` needed. It also re-syncs the source repo to its default branch first, per the Reference Repo Policy.)

After the worktree is recreated, autonomously add it back to `<work-sessions-repo>/work-sessions.code-workspace` if an entry for it doesn't already exist (same format as `#create_work_tree.prompt.md` step 4).

### 7. Update status and orient the user

Update `<work-sessions-repo>/SESSIONS_STATE.md`: find the row for this session and set **Status** to `active` and **Last Change** to today. Autonomous — no approval needed.

Tell the user:
- Session is active: `<work-sessions-repo>/sessions/<session-id>/`
- Agentic-sdlc tools worktree refreshed (note if it advanced)
- tmux session ready — `tmux attach -t cw-<session-id>`
- Target-repo worktrees ready (list paths)
- Remind of tasks (from `TASKS.md`) and current-state description
- Engineering defaults: `TDD · BDD · Design-first · Well-Architected · KIS`
- Available commands:
  - `#sync-work.prompt.md` — commit and push at any point
  - `#review-pr.prompt.md` — address PR review comments
  - `#create-adr.prompt.md` — document a decision
  - `#create_work_tree.prompt.md` — add another target repo
  - `#pause_work_session.prompt.md` — save state
  - `#stop_work_session.prompt.md` — hard stop, keep branches
  - `#end_work_session.prompt.md` — close out when done
