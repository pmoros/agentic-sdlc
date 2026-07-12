# Sync Work

Stage, commit, and push the current state of work in one of the active
session's target-repo worktrees. Safe to run at any time during a session,
as many times as needed.

## Steps

### 1. Identify the worktree

If the current working directory is already inside a session's worktree, use
it directly. Otherwise: read `<work-sessions-repo>/SESSIONS_STATE.md`
(sibling `../work-sessions` of this repo) for the active
session, then list `ls <work-sessions-repo>/sessions/<session-id>/worktrees/`
excluding `agentic-sdlc` (that one is read-only tooling — never has work to
sync). If more than one target-repo worktree exists, ask which to sync.

### 2. Check git status

Run `git -C <worktree-path> status` and show the full output. If the working tree is clean (nothing to commit, nothing staged), inform the user and stop.

### 3. Propose what to stage

Ask:
> "Which files should be staged? (all / specific paths — list them)"

Stage as directed. Then run `git -C <worktree-path> diff --cached --stat` and show the staged summary.

### 4. Propose a commit message

Inspect the staged diff and propose a Conventional Commits message:
- Infer the type from the nature of the changes (`feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, etc.)
- Infer the scope from the file paths or session context if available
- Write a concise, imperative-mood description

Show the proposed message:
```
<type>(<scope>): <description>
```

Ask: "Use this commit message, or edit it?" — wait for confirmation or the user's version.

The final message must be Conventional Commits compliant. Correct it if it is not before proceeding.

### 5. Commit

Show the full commit command and **wait for explicit approval before running**:
```bash
git -C <worktree-path> commit -m "<approved message>"
```

### 6. Push

Ask:
> "Push to remote now? (yes / no)"

If yes, show the command and **wait for explicit approval before running**:
```bash
git -C <worktree-path> push origin <branch-name>
```
If this is the first push for the branch (no upstream set), use:
```bash
git -C <worktree-path> push --set-upstream origin <branch-name>
```

### 7. Update session file

Update `<work-sessions-repo>/sessions/<session-id>/CONTEXT.md`: append to `## Activity log`:
```
- <YYYY-MM-DD HH:MM> pushed <branch-name> to origin (<repo-name>)
```
This is autonomous — no approval needed.
