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

### 2b. Confluence re-check

Load `.agents/rules/atlassian.instructions.md` for the Confluence space
table and CQL discovery guidance, and read the session's `CONTEXT.md` for
its `## Related Wiki` table (added by the `start-work-session` skill's
matching step). If that heading is entirely absent, this session predates
the step — skip re-checking and note nothing here.

Re-ask: "Same Confluence space(s) as at session start (list them), any
different/additional ones, or none?" Re-run the CQL search (space(s) +
ticket key/goal keywords, per `atlassian.instructions.md`), informed by what
actually happened this session (skim `WORKLOG.md`/`TASKS.md`). Surface any
new candidate pages; ask which to add. **Append** new rows to the existing
`## Related Wiki` table — never remove or edit prior rows.

If there is nothing new to link, say so explicitly in the WORKLOG entry
(step 4) — `Confluence: nothing new to link` (deliberately distinct
wording from step 4b's batch-level "Nothing to document" — this one covers
Confluence discovery only, not the whole external-write batch) — rather
than leaving it unmentioned. A skipped check and a checked-and-empty result
must never look the same in the record.

### 3. Check git state

List the session's target-repo worktrees: `ls <work-sessions-repo>/sessions/<session-id>/worktrees/` excluding `agentic-sdlc`. For each, determine its branch and verify it has been pushed and a PR exists. If either is missing, display:

> ⚠ **Before closing:** It looks like `#sync-work.prompt.md` and/or `#open-pr.prompt.md` have not been run for `{repo-name}`.
> - Branch pushed? [yes / no]
> - PR open? [yes / no]
>
> You can proceed without these, but work on this branch may not be visible to your team. Continue anyway? (yes / no)

Do not block session closure if the user chooses to continue.

### 4. Update session files

Load `.agents/rules/session-state.instructions.md` for the current file
conventions, then update `<work-sessions-repo>/sessions/<session-id>/CONTEXT.md`:
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

If step 2b found nothing new to link, add `Confluence: nothing new to link` to the same entry — never omit it silently.

Also update `<work-sessions-repo>/SESSIONS_STATE.md`: find the row for this session and set **Status** to `done` and **Last Change** to today.

All file writes are autonomous.

### 4b. Assemble and approve the batched close-checkpoint

Everything external is assembled **first** and approved **once** — never
write to Jira/Confluence piecemeal (ADH-008 Phase 8; see `SPEC.md` §9). A
declined batch changes nothing locally; the same delta re-proposes next
time this session closes.

Load `.agents/rules/atlassian.instructions.md` before this step.

1. **Determine the item and watermark.** Read
   `<work-sessions-repo>/work/items/<session-id>.json` (the canonical
   item). Note its `last_synced` field, if any — everything in `history`
   with a `timestamp` after that watermark (or the whole `history`, if
   there's no watermark yet) is "since last sync."

2. **Plan the Jira transition(s)**, only if the item has a
   `tickets.main-bug-tracking` entry (a bare key like `IO-101` or a full
   `/browse/IO-101` URL — extract the key either way):
   - Call the get-transitions tool for the current issue — **never assume**
     the current state (existing pre-flight rule above).
   - If a transition to a "done"/complete-reading status is directly
     available, plan that single hop.
   - If not, this workflow needs a **chain** (e.g. this org's `IO` project:
     `In Progress → IN REVIEW → IN TESTING → READY TO DEPLOY → Done`, no
     direct hop). Confirm the intended target status with the user, then
     draft a **provisional plan** for the full sequence, reasoning from the
     confirmed goal and the documented workflow shape (e.g. the worked
     example above) — you cannot literally call get-transitions for a status
     the issue isn't at yet, since that tool is scoped to the issue's actual
     current state. Show this full provisional chain in the batch (step 5)
     so the single approval covers the intended path end-to-end. Hop 1's
     options come from a real get-transitions call against the issue's
     actual current status; hops 2+ are confirmed for real only when step 6
     reaches them and re-checks get-transitions immediately before firing
     each one — that live re-check, not the plan, is what actually verifies
     them.
   - If none of the available transitions plausibly lead toward completion
     (e.g. only `Reopen` is offered), plan **no transition** and say so
     explicitly in the batch — "No applicable Jira transition available:
     <list>" — rather than silently omitting the Jira part of the batch.
   - Draft **one** consolidated comment summarizing what happened since the
     watermark (question 1's summary + notable `history` entries) — not a
     transition-by-transition dump.

3. **Propose Confluence updates.** For each row in `CONTEXT.md`'s
   `## Related Wiki` table (added by `start-work-session`, re-checked in
   step 2b), draft a **footer comment** — not a page edit; this command
   doesn't have enough context to safely rewrite page content — noting the
   session's outcome and linking back to the ticket/PR. Nothing to propose
   if the table is empty or absent.

4. **"Also touches" items.** No mechanism currently tracks which other
   items a session's work also affects (see
   `docs/gap-analysis-target-architecture.md`) — this is a deliberate no-op
   until one exists. Do not invent one ad hoc.

5. **Show the full batch** — the full planned Jira transition sequence (or
   the explicit "no applicable transition" note) + comment, and every
   proposed Confluence footer comment, verbatim — and ask: "Apply all?
   (yes / no / edit)". On "edit," let the user restate what should change,
   regenerate the batch, and show it again. If there is **nothing** to
   propose at all (no ticket, no Related Wiki rows, nothing since the
   watermark), the batch must say so explicitly — **"Nothing to
   document — no Jira ticket, no Related Wiki pages, and no ticket-worthy
   history since the last sync."** Never silently skip this step.

6. **On "yes," execute and verify each response** (per
   `atlassian.instructions.md`'s "never assume success" rule):
   - Walk the planned transition sequence **one hop at a time**. Before
     firing each hop, re-call get-transitions to confirm it's still offered
     from the issue's *current* state — a workflow can change out from
     under a multi-step close (e.g. another automation firing mid-sequence).
     If a planned hop is no longer available, **stop the chain there**;
     still apply the comment and every Confluence update regardless. Report
     exactly which status the ticket was left at and name the remaining
     hops as a follow-up in the close summary (step 6/`WORKLOG.md`) — do
     **not** keep the session's worktrees around just to retry; the ticket
     is discoverable and finishable later (e.g. via `#review-wip`) even
     after this session is fully closed.
   - Then the comment, then each Confluence footer comment in turn.
   - Surface any failure immediately; do not silently continue past one.

7. **Record the watermark** — after every response in the batch succeeds
   (or immediately, if the batch was "nothing to document"):
   ```bash
   scripts/define-work-item.sh <session-id> --last-synced <ISO 8601 now> \
     --work-sessions-repo <work-sessions-repo>
   ```
   On "no," do **not** advance the watermark — the same delta must
   re-propose next close.

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
- The close-checkpoint outcome from step 4b — what was applied (Jira transition, comments, Confluence footer comments), or that there was nothing to document
- Worktrees removed (list each); branches retained in their source repos
- VS Code workspace updated; tmux session `cw-<session-id>` killed
- Follow-up tasks noted (list them)
- Suggest next step: `#find-session.prompt.md` to review other open sessions, or the `start-work-session` skill for a follow-up task
