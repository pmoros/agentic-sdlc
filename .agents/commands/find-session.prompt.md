---
agent: agent
description: Search and list active, paused, or stopped work sessions by description or status.
---

# Find Session

This is a read-only command. It does not modify any files.

## Step 1 — Collect search criteria

Ask the user (one question, answers can be combined):

> "What are you looking for? You can describe the work (e.g. 'oauth refresh token fix'), filter by status (`active` / `paused` / `stopped` / `done` / `all`), or both. Press Enter to list all sessions."

If the user presses Enter or says "all", skip filtering and show every session.

## Step 2 — Read SESSIONS_STATE.md

Read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo) as the primary index. If the file has no real rows (only the `_none yet_` placeholder), respond:

> "No sessions found. Start one with the `start-work-session` skill."

Extract from each row: **Session ID**, **Title**, **Session Folder**, **Created**, **Last Change**, **Status**.

For each session, optionally enrich with live data from `<work-sessions-repo>/sessions/<Session Folder>/CONTEXT.md` if detail is needed:
- **Ticket** — the `main` row of the Tickets table
- **Last activity** — last line of `## Activity log`
- **Current state** — the `- **Description:**` line

## Step 3 — Filter and match

If the user provided a text query:
- Match against: **Session ID**, **Title**, and **Session Folder** name
- Case-insensitive substring match is sufficient
- If status filter was given, apply it as an AND condition

## Step 4 — Display results

Present a table:

```
| ID | Title | Status | Last Change | Folder |
|----|-------|--------|-------------|--------|
| PROJ-123 | OAuth Refresh | active | 2026-03-10 | PROJ-123-oauth-refresh |
| ADH-001  | Update copilot flows | paused | 2026-03-12 | ADH-001-update-copilot-flows |
```

If no sessions match the query, show the full list with a note:

> "No sessions matched your query. Showing all sessions:"

## Step 5 — Offer next action

After displaying the table, prompt:

> "To resume a session, run `#resume_work_session.prompt.md` and reference the session ID or folder name above."

Do not automatically resume or modify anything — this command is read-only.
