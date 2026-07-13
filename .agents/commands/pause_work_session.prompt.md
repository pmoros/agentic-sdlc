# Pause Work Session

You are pausing an active work session. This saves current state to the
session files in `work-sessions` and optionally commits staged
work in one of its worktrees. Branches and worktrees remain intact.

## Steps

### 1. Identify the active session

Read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo) and filter rows with `Status: active`.

- If exactly one is found, use it.
- If multiple are found, list them (session ID + title) and ask the user which to pause.
- If none are found, inform the user there is no active session and stop.

### 2. Ask status questions

Ask the user each of the following in sequence. Do not skip or combine.

1. **Current status** — `in-progress | blocked | waiting-for-review`
2. **What was accomplished since last start/resume?** — brief bullet list (e.g. "Added auth middleware, Fixed token expiry bug")
3. **Immediate next step when resuming** — one sentence
4. **Open blockers or questions** — (press Enter for none)

### 3. Update session files

Load `.agents/rules/session-state.instructions.md` for the current file
conventions, then update `<work-sessions-repo>/sessions/<session-id>/CONTEXT.md`:
- Set `- **Blocked:**` to `yes` if question 1 is `blocked`, else `no`.
- Set `- **Description:**` to question 3's next-step sentence, prefixed with question 1's status if not plain `in-progress` (e.g. `waiting-for-review — <next step>`).
- Append to `## Activity log`:
  ```
  - <YYYY-MM-DD HH:MM> session paused — <one-line summary of question 2>
  ```

If question 4 has content, note it in the same Description line or as a follow-up Activity log entry.

These file writes are autonomous — no approval needed (session file read/write is autonomous per the Git Policy table in `AGENTS.md`).

Also update `<work-sessions-repo>/SESSIONS_STATE.md`: find the row for this session and set **Status** to `paused` and **Last Change** to today. Autonomous.

### 4. Commit staged work

List the session's target-repo worktrees: `ls <work-sessions-repo>/sessions/<session-id>/worktrees/` excluding `agentic-sdlc` (that one is read-only tooling, never has work to commit). If there is more than one, ask which worktree this commit is for.

Run `git -C <worktree-path> status` and show the summary. Ask:
> "Which files should be staged for this commit? (all / specific paths / none — press Enter to skip commit)"

If the user wants to commit:
- Stage as directed
- Inspect the diff and propose a Conventional Commits message
- Show the full proposed commit command and **wait for explicit approval before running `git commit`**

### 5. Orient the user

Remind the user:
- Session state saved at `<work-sessions-repo>/sessions/<session-id>/`
- Worktrees remain in place at `<work-sessions-repo>/sessions/<session-id>/worktrees/`
- Resume any time with `#resume_work_session.prompt.md`

**Recommend ending this conversation now.** File state is the durable
record — this chat is not. `#resume_work_session.prompt.md` is designed to
run in a fresh conversation; continuing this one across the break is the
main way a session's context (and cost) grows unbounded. See `AGENTS.md` §
Model & Context Discipline.
