# Override Tool Priority

Temporarily inverts the default MCP-first tool priority for one or more named tool groups, forcing CLI or direct API usage instead. The override is **scoped to the current task or explicit duration** — once that scope ends, MCP-first priority is automatically restored.

**Default priority** is MCP-first, defined canonically in the rules — GitHub in
`.agents/rules/github.instructions.md`, Atlassian in
`.agents/rules/atlassian.instructions.md`. This command does not redefine it;
it temporarily flips it. Run this command to flip a tier for a bounded window,
then run it again (or complete the scope) to revert.

---

## Steps

### 1. Identify scope

Ask:
> "What scope should this override apply to?
> - **task** — applies until you explicitly say the task is done (you'll be prompted to revert)
> - **next N operations** — applies for the next N tool calls, then auto-reverts (e.g. `next 3`)
> - **rest of session** — applies until the session ends (use sparingly)"

Record the scope as `<override-scope>`.

### 2. Select tool groups to override

Present the known tool groups:

```
ID   Domain              MCP tool pattern          CLI / API fallback
──   ──────────────────  ────────────────────────  ─────────────────────────────────
1    GitHub              mcp_github_*              gh CLI
2    GitHub (PR only)    github-pull-request_*     gh CLI
3    Atlassian Jira      mcp_mcp-atlassian_jira_*  Atlassian REST API (curl/fetch)
4    Atlassian Confluence mcp_mcp-atlassian_conf*  Atlassian REST API (curl/fetch)
5    All Atlassian       mcp_mcp-atlassian_*       Atlassian REST API (curl/fetch)
6    All of the above    (everything)              respective CLI/API per domain
```

Ask:
> "Which tool groups should use CLI/API instead of MCP? Enter IDs separated by commas (e.g. `1,3`), or describe what you need."

If the user describes rather than lists IDs, map their description to the closest group(s) and confirm.

### 3. Confirm the override

Show a summary and **wait for explicit confirmation**:

```
Tool priority override — <override-scope>

FLIPPED (CLI/API first, MCP skipped):
  [for each selected group]
  - <domain>: <CLI/API fallback> will be used instead of <MCP pattern>

UNCHANGED (MCP-first still applies):
  [remaining groups not selected]

Reason for override: <ask user to state reason in one line — required for activity log>
```

Ask: "Apply this override? (yes / no)"

### 4. Update the session file (if a session is active)

Find the active session in `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo; `Status: active`). If found, in that session's `CONTEXT.md`:
- Append to `## Activity log`:
  ```
  - <YYYY-MM-DD HH:MM> tool priority override activated — <groups> → CLI/API (<scope>)
  ```
- If `rest of session` scope: also note the standing override in the Current state `- **Description:**` line so it's visible on resume.

If no active session is found, the override is conversation-scoped only — note this to the user.

### 5. Apply the override

State clearly:
> "**Tool priority override is now active.** For the scope declared above, I will use `<CLI/API>` instead of `<MCP pattern>` for all `<domain>` operations. I will not attempt the MCP tool first during this window."

Maintain this behaviour for the declared scope. Do not silently revert early.

### 6. Revert

**task scope:** After completing the declared task, prompt:
> "Task complete. Reverting tool priority to MCP-first for `<groups>`. Confirm? (yes / no)"

**next N operations scope:** After the Nth tool call in the overridden groups, automatically state:
> "Tool priority override has expired (N operations completed). Reverting to MCP-first for `<groups>`."

**rest of session scope:** Revert when the session ends (`#end_work_session.prompt.md` or `#stop_work_session.prompt.md`).

On revert, if a session is active, append to its `CONTEXT.md` `## Activity log`:
```
- <YYYY-MM-DD HH:MM> tool priority override reverted — MCP-first restored for <groups>
```
And clear any standing-override note from the Current state `- **Description:**` line if it was set.
