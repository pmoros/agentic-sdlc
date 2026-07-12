---
agent: agent
description: Set up or update Jira and GitHub integration schemas (templates, field names, PR conventions). Additive — reads existing files before proposing changes.
---

# Configure Integrations

This command is **additive**: it always reads existing integration files before proposing changes and never overwrites without showing a diff first.

## Step 0 — Ensure gitignore entries exist

Check `.gitignore` for the following entries. If any are missing, add them:

```
.agents/rules/*.local.*
.github/instructions/*.local.*
```

## Step 1 — Select integration to configure

Ask:

> "Which integration would you like to configure?
> (A) Atlassian (Jira / Confluence)
> (B) GitHub (PRs, labels, review checklist)
> (C) Both"

---

## Flow A — Atlassian

### A1 — Read existing files

Check for `.agents/rules/atlassian.instructions.md` and `.agents/rules/atlassian.local.instructions.md`. If they exist, display their current contents and note what will be updated vs preserved.

### A2 — Structural schema (committed)

Gather the following for `atlassian.md` (will be committed — no personal data):

1. **Project name / context**: What is the Jira project this repo maps to? (e.g. "Backend API — PROJ board")
2. **Issue types**: What issue types does the team use? (e.g. Story, Task, Bug, Spike, Sub-task)
3. **Custom field names**: Are there any custom fields used in tickets? (e.g. "Story Points → `story_points`", "Epic Link → `epic_link`")
4. **Workflow states**: What are the column names in the board? (e.g. Backlog → In Progress → In Review → Done)
5. **Sprint naming convention**: How are sprints named? (e.g. `Sprint <N>` or `<team>-<YYYY>-W<NN>`)
6. **Ticket template**: What fields does a well-formed ticket include? (accept free text or bullet list)
7. **Create-path constraints**: Are there issue-type-specific required fields, hidden request-type fields, or known MCP limitations that must be recorded? Capture exact field IDs, allowed values, and failure messages when known.

When writing `atlassian.md`, make the Jira create path explicit enough that `#start_work_session` can create tickets directly from it via MCP without guessing. Record:
- whether Jira creation must prefer `mcp_mcp-atlassian_jira_create_issue`
- which defaults belong in `additional_fields`
- which fields are required per issue type
- which values are allowed for each constrained field
- whether description/comment text must be markdown rather than Jira wiki markup

If an Atlassian MCP server is available and connected, offer to auto-detect project keys, boards, and field names rather than asking manually.

### A3 — Personal schema (gitignored)

Gather the following for `atlassian.local.md` (gitignored — personal context only):

1. **Jira project key(s)**: e.g. `PROJ`, `BACK`
2. **Board or sprint filter**: Which board or sprint should `#start_work_session` reference when suggesting tickets?
3. **Environment variable names**: What env vars hold Jira credentials? (e.g. `JIRA_API_TOKEN`, `JIRA_EMAIL`)

### A4 — Show diff and confirm

Display the full proposed content for both files. Ask:

> "Does this look right? I'll write both files once you confirm."

Write files after approval:
- `.agents/rules/atlassian.instructions.md` — structural schema (commit this)
- `.agents/rules/atlassian.local.instructions.md` — personal schema (gitignored)

---

## Flow B — GitHub

### B1 — Read existing files

Check for `.agents/rules/github.instructions.md` and `.agents/rules/github.local.instructions.md`. Display current contents if they exist.

### B2 — Structural schema (committed)

Gather the following for `github.md`:

1. **PR title convention**: Does the team follow a convention? (default: Conventional Commits — `<type>(scope): description`)
2. **PR body template**: What sections should a PR include? (default: Summary, Changes, Testing, Checklist)
3. **Label taxonomy**: What labels does the team use? (e.g. `bug`, `enhancement`, `breaking-change`, `needs-test`)
4. **Review checklist**: What items must a reviewer verify before approving? (accept bullet list)
5. **Branch protection rules** (informational): Are there required checks or min approvals to note?

### B3 — Personal schema (gitignored)

Gather the following for `github.local.md`:

1. **Default reviewers**: Who do you typically request review from? (GitHub usernames)
2. **Draft vs ready-for-review default**: Should `#open-pr` default to draft PRs or ready-for-review?
3. **Target branch default**: What is the default merge target? (e.g. `main`, `develop`)

### B4 — Show diff and confirm

Display the full proposed content for both files. Ask:

> "Does this look right? I'll write both files once you confirm."

Write files after approval:
- `.agents/rules/github.instructions.md` — structural schema (commit this)
- `.agents/rules/github.local.instructions.md` — personal schema (gitignored)

---

## Flow C — Both

Run Flow A then Flow B sequentially. Confirm each before proceeding to the next.

---

## Completion

After writing all files, confirm:

> "Integration schemas written. Structural files (`atlassian.md`, `github.md`) can be committed. Personal files (`*.local.md`) are gitignored and will not be tracked."

If any structural file is new, remind the user to commit it:

> "Run `#sync-work.prompt.md` to stage and commit the new integration schema."
