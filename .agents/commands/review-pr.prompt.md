# Review PR

Triage and address pull request review comments, or give structured feedback on someone else's PR. This command is re-runnable at any point in the review cycle.

## Tool Priority

Always prefer GitHub MCP tools over `gh` CLI. Before any GitHub operation, load tools with `tool_search_tool_regex` using pattern `mcp_github_`. Fall back to `gh` CLI only if the required MCP tool does not exist after searching.

**MCP → CLI mapping for this command:**
| Operation | MCP tool (preferred) | CLI fallback |
|---|---|---|
| Get PR details | `mcp_github_pull_request_read` | `gh pr view <number> --json ...` |
| Get PR diff | `mcp_github_pull_request_read` | `gh pr diff <number>` |
| Submit review | `mcp_github_pull_request_review_write` | `gh pr review <number> --body-file ...` |
| Reply to comment | `mcp_github_add_reply_to_pull_request_comment` | N/A |

## Step 0 — Mode selection

Ask first, before doing anything else:
> "Are you **(A) the author** addressing comments on your own PR, or **(B) a reviewer** giving feedback on someone else's PR?"

Branch into the appropriate mode below.

---

## Mode A — Author: addressing comments on your own PR

### A1. Load the PR
Look for the PR URL in the active session's `work/wip.json` (the item's `work_items`) or its `CONTEXT.md`. If not found, ask:
> "Enter the PR number or URL for this branch:"

Fetch all review threads using `mcp_github_pull_request_read` (preferred) or as fallback:
```
gh pr view <number> --json reviewThreads,comments
```

### A2. Triage threads
Categorize each unresolved thread by action type:

| Category | Meaning |
|---|---|
| **must-fix** | Blocking approval — correctness issue, security concern, or reviewer explicitly requested a change |
| **suggestion** | Non-blocking improvement proposed by reviewer |
| **question** | Reviewer asking for clarification — reply needed, no code change required |
| **nit** | Style or cosmetic — low priority, reviewer explicitly marked it as minor |

Display a grouped summary table:
```
Category    File                  Line  Reviewer     Comment (excerpt)
must-fix    src/auth/token.ts     42    alice        "This will cause null pointer if..."
suggestion  src/utils/format.ts   18    bob          "Consider using optional chaining here"
question    README.md             —     carol        "What is the retry backoff strategy?"
nit         src/api/client.ts     99    alice        "Trailing space"
```

Ask: "Work through all **must-fix** items first, or pick specific threads by number?"

### A3. Address loop (per thread)
For each selected thread:

1. Navigate to the relevant file and line — show surrounding code context (±10 lines)
2. Display the full thread (original comment + all replies)
3. Ask:
   > "How do you want to handle this?
   > **(a)** Draft a code fix
   > **(b)** Draft a reply
   > **(c)** Skip with reason"

**On choice (a) — Draft a fix:**
- Agent proposes a concrete code change and displays it as a diff
- Ask: "Apply this change? (yes / edit / skip)"
- On yes: apply the file edit. Do NOT commit — `#sync-work.prompt.md` handles that.

**On choice (b) — Draft a reply:**
- Agent drafts a reply text based on the context
- Show draft and ask: "Use this reply text, edit it, or skip?"
- Record the approved reply text in session notes — agent does NOT post to GitHub API

**On choice (c) — Skip:**
- Ask: "Reason for skipping?" (e.g. "out of scope", "disagree — will discuss in review")
- Record in local tally

### A4. Wrap-up
Show a summary:
```
Threads addressed (code fix applied): N
Threads replied to (reply drafted):   N
Threads skipped:                      N
Threads deferred:                     N
```

Remind the user:
- Run `#sync-work.prompt.md` to commit and push the applied fixes
- Reviewers resolve their own threads after reviewing the pushed changes
- Optionally run `#open-pr.prompt.md` to refresh the PR description if the summary changed significantly

---

## Mode B — Reviewer: giving feedback on someone else's PR

### B1. Load the PR
Ask:
> "Enter the PR number or URL to review:"

Fetch PR metadata and diff using `mcp_github_pull_request_read` (preferred) or as fallback:
```
gh pr view <number> --json title,body,author,baseRefName,headRefName,changedFiles,additions,deletions
gh pr diff <number>
```

Display an overview:
```
PR:     #<number> — <title>
Author: <author>
Base:   <base> ← <head>
Size:   +<additions> / -<deletions> across <N> files
Linked: <issue URL or none>
```

### B2. Review loop (per file or logical group)
Walk through changed files one at a time. For each file:
1. Show the diff with context
2. Display any existing review comments on that file (if any)
3. Ask: "Any comments on this section? (yes / no / skip file)"

**On yes:**
- Ask the user to describe their concern in natural language
- Agent drafts a formal review comment based on the concern
- Show the draft and ask: "Use this comment, edit it, or discard?"
- Approved comments are accumulated in a local review draft — nothing is posted yet

### B3. Overall assessment
After all files, ask:
> "What is your overall verdict?
> **(a)** Approve
> **(b)** Request changes
> **(c)** Comment only (no verdict)"

### B4. Submit review
Show the full review draft — all accumulated comments + verdict. Ask the user to confirm or adjust.

Show the full review and **wait for explicit approval before submitting**.

**Preferred — MCP:**
Call `mcp_github_pull_request_review_write` with the accumulated inline comments and overall body text.

**Fallback — CLI (only if MCP tool not available):**
Write the review body to the session's tmp folder (never `/tmp/`):
```
<work-sessions-repo>/sessions/<session-id>/tmp/review-<pr-number>-<YYYYMMDD-HHmmss>.md
```
Then run:
```
gh pr review <number> --<approve|request-changes|comment> --body-file <work-sessions-repo>/sessions/<session-id>/tmp/review-<pr-number>-<YYYYMMDD-HHmmss>.md
```

Output the confirmation and review URL.
