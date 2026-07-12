# Open PR

Create a new pull request or refresh an existing one. This command is idempotent — safe to run again after major changes to update the PR description.

## Tool Priority

Always prefer GitHub MCP tools over `gh` CLI. Before any GitHub operation, load tools with `tool_search_tool_regex` using pattern `mcp_github_`. Fall back to `gh` CLI only if the required MCP tool does not exist after searching.

**MCP → CLI mapping for this command:**
| Operation | MCP tool (preferred) | CLI fallback |
|---|---|---|
| Get existing PR | `mcp_github_list_pull_requests` | `gh pr view --json number,title,url,state` |
| Create PR | `mcp_github_create_pull_request` | `gh pr create --body-file ...` |
| Update PR | `mcp_github_update_pull_request` | `gh pr edit <number> --body ...` |
| List commits | `mcp_github_list_commits` | `git log origin/<default>...<branch> --oneline` |

## Steps

### 1. Detect existing PR
Search for an open PR on the current branch using `mcp_github_list_pull_requests` (filter by head branch). If MCP is unavailable, fall back to:
```
gh pr view --json number,title,url,state
```
If this also fails, ask the user: "Does a PR already exist for this branch? (yes / no / unknown)"

---

### If PR already exists → Refresh mode

Show the current PR title and URL. Ask:
> "The PR already exists. Would you like to refresh the description with the latest session context? (yes / no)"

If yes, jump to **Step 3** to build an updated body. Then:
- Show the proposed updated body
- **Wait for explicit approval**, then update using `mcp_github_update_pull_request` (preferred) or `gh pr edit <number> --body "<updated body>"` (fallback)
- Confirm the update and output the PR URL.

---

### If PR does not exist → Create mode

### 2. Gather PR context
Collect the following from available sources (in priority order):

- **Session files** (`<work-sessions-repo>/sessions/<session-id>/CONTEXT.md` and `PLAN.md`, in the sibling `../work-sessions`): goal, ticket, scope, tasks; find the session from the current worktree or the `Status: active` row in `SESSIONS_STATE.md`
- **Integration template** (`.agents/rules/github.instructions.md`): PR body template, checklist, and conventions
- **Integration local file** (`.agents/rules/atlassian.local.instructions.md`): Jira project key / ticket URL to link, if present
- **Commits**: use `mcp_github_list_commits` (preferred) or `git log origin/<default-branch>..<branch> --oneline` (fallback)

### 3. Draft the PR body
Produce a draft using the following structure (adapt if `github.md` template provides a different structure):

```markdown
## Summary
<2–4 sentences describing what this PR does and why>

## Changes
<bullet list of key changes — inferred from commits and session checklist>

## Linked Ticket
<Jira URL or N/A>

## Testing
<how the changes were tested, or "N/A — documentation only">

## Checklist
<items from github.md checklist template, or a sensible default>
- [ ] Tests added or updated
- [ ] Documentation updated
- [ ] No secrets or credentials committed
- [ ] Breaking changes documented (if any)
```

Show the full draft to the user. Ask: "Edit the body before creating, or use as-is?"

### 4. Confirm PR metadata
Ask or confirm:
1. **PR title** — propose: `<type>(<scope>): <description>` (Conventional Commits; see `.agents/rules/github.instructions.md`); user confirms or edits
2. **Target branch** — default: `main` (or repo default); ask if different
3. **Draft or ready for review?** — `draft | ready`

If a ticket is linked, ensure the **Linked Ticket** section in the body contains the Jira URL (not the PR title).

### 5. Create the PR

Show the full PR details and **wait for explicit approval before creating**.

**Preferred — MCP:**
Call `mcp_github_create_pull_request` with:
- `title`: the confirmed PR title
- `body`: the approved PR body text
- `base`: target branch
- `draft`: `true` or `false`

**Fallback — CLI (only if MCP tool not available):**
Write the PR body to the session's `tmp/` folder first — **never** `/tmp/` or any shared system folder:
```
<work-sessions-repo>/sessions/<session-id>/tmp/pr-body-<YYYYMMDD-HHmmss>.md
```
Then run (from the target repo's worktree):
```
gh pr create \
  --title "<title>" \
  --body-file <work-sessions-repo>/sessions/<session-id>/tmp/pr-body-<YYYYMMDD-HHmmss>.md \
  --base <target-branch> \
  [--draft]
```

### 6. Record PR URL
Output the PR URL to the user. If a session is active, record it (autonomous, per the session-state rule):
- add the URL to that item's `work_items` in `<work-sessions-repo>/work/wip.json`, and
- log it: `scripts/session-log.sh <session-id> "opened PR <url>"`.
