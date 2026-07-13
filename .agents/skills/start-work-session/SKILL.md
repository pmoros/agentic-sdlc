---
name: start-work-session
description: >
  Starts a new work session: gathers ticket/goal/scope details, initializes
  the session folder in work-sessions (via
  initialize_work_session_folder — which always sets up a detached, in-sync
  worktree of this repo for tool access), then creates a worktree per target
  repo (via create_work_tree). Use for "start a work session", "start work
  on <ticket>", "new session for <task>", or any request to begin a new
  piece of work.
---

# Start Work Session

High-level orchestration for beginning a new piece of work. This skill
gathers the details, then delegates the mechanical, script-backed steps to
two atomic commands:

- `initialize_work_session_folder` — creates the session folder in
  `work-sessions` and its mandatory `worktrees/agentic-sdlc`
  worktree.
- `create_work_tree` — creates one worktree per target repo.

Run this from the `agentic-sdlc` reference checkout under
`repos/` (not from inside another session's worktree) — the
scripts default to treating wherever they live as the source-of-truth repo.

## Steps

### 1. Repo doctrine reminder

Read `.copilot-doctrine.md` at this repo's root if it exists, and display:

```
── Doctrine reminder ──────────────────────────────────────────────
Repo: <repo name>
North star: <char 1> · <char 2> · <char 3>
Engineering defaults: TDD · BDD · Design-first · Well-Architected · KIS
──────────────────────────────────────────────────────────────────
```

If not found, inform the user:
> "No `.copilot-doctrine.md` found. Consider running `#set-repo-doctrine.prompt.md` first. You may continue without it."

Still show the engineering defaults reminder either way. If a target repo
(step 2) has its own `.copilot-doctrine.md`, show its reminder too once that
repo's worktree exists (step 4).

### 2. Identify target repos

Ask:
> "Is this session working in the agentic-sdlc tools only, or also targeting one or more repos under `repos/`? List any target repo names or paths, or press Enter for tools-only."

Record the list (may be empty). Every session gets a worktree of
`agentic-sdlc` automatically regardless of this answer — that
is not something to ask about (see step 3). Each listed target repo always
gets its own worktree (step 4) — per the Reference Repo Policy in `AGENTS.md`,
there is no branch-only/no-worktree option; direct edits to a repo checkout
under `repos/` are never allowed.

### 3. Gather session info

Ask the user each of the following in sequence. Wait for all answers before proceeding.

1. **Task type** — choose one: `feat | fix | chore | refactor | docs | spike`
2. **Ticket / issue ID** — paste an existing ID/URL, type `new` to create one now, or press Enter to skip
3. **Short description** — slug format: lowercase, hyphens only, max 4 words (e.g. `oauth-refresh`, `bulk-upload-retry`, `update-readme`)
4. **One-line goal** — full sentence describing what this session will accomplish
5. **Scope estimate** — `XS | S | M | L | XL`
6. **Known dependencies or blockers** — (press Enter for none)

#### Determine the Session ID

After collecting question 2:
- **Ticket provided:** extract the key from the ticket ID or URL (e.g. `PROJ-6025` from `https://yourcompany.atlassian.net/browse/PROJ-6025`). Use that key as the Session ID.
- **No ticket:** read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo) and find the highest existing `ADH-NNN` number. Increment by 1. If none exist, assign `ADH-001`.

#### Ticket creation (only when question 2 = `new`)

Ask in sequence:
1. **Ticketing system** — `jira` (default) or `github-issue`
2. **Project / repo** — Jira project key (e.g. `PROJ`) or GitHub `owner/repo`
3. **Issue title** — defaults to the short description from question 3 if left blank
4. **Issue type** *(Jira only)* — e.g. `Story | Task | Bug | Spike` (press Enter for `Task`)
5. **Description** — brief summary, or press Enter to use the one-line goal from question 4

Then create the ticket using the appropriate MCP tool (following tool priority rules):
- **Jira:** `tool_search_tool_regex` pattern `mcp_mcp-atlassian`, then `mcp_mcp-atlassian_jira_create_issue`. Fallback: Atlassian REST API.
- **GitHub issue:** `tool_search_tool_regex` pattern `mcp_github`, then `mcp_github_issue_write`. Fallback: `gh issue create`.

For **Jira** ticket creation, read `.agents/rules/atlassian.instructions.md` before calling the tool and treat it as the source of truth for create-time defaults and constraints — see that file for the full field contract, defaults, and known MCP quirks.

After creation, display the ticket ID and URL. Use the new ticket ID as the answer to question 2 and continue.

If ticket creation fails, ask: "Skip ticket and continue without one, or retry? (skip / retry)"

---

From the answers, construct the branch name:
- With ticket ID: `<type>/<ticket-id>-<description>` (e.g. `feat/PROJ-123-oauth-refresh`)
- Without ticket ID: `<type>/<description>` (e.g. `feat/oauth-refresh`)

Show the constructed branch name and ask: "Confirm branch name or edit:"

The session folder name is the branch slug without the type prefix (e.g.
`feat/PROJ-6025-webflow-geo-tracking` → `PROJ-6025-webflow-geo-tracking`).

### 4. Initialize the session folder

Invoke `initialize_work_session_folder` with the gathered session ID, goal,
ticket, scope, task type, and blockers. This creates
`<work-sessions-repo>/sessions/<session-name>/` from the template, registers
it in `SESSIONS_STATE.md`, **upserts the matching `in progress` item into the
portfolio work tracker `work/wip.json`** (moving it from `work/backlog.json`
if it was groomed there, otherwise seeding it from the session
goal/ticket/scope/task-type — so starting a session never leaves the tracker
empty for that id), and creates the mandatory `worktrees/agentic-sdlc`
worktree — all autonomous, no separate approval needed (session file
read/write and worktree add/remove are both autonomous per the Git Policy
table in `AGENTS.md`).

### 5. Create a worktree per target repo

For each target repo named in step 2, invoke `create_work_tree` with that
repo, the confirmed branch name, and a base ref (default: the repo's
auto-detected default branch; use `develop` for the `code` monorepo unless
the user says otherwise).

### 6. Confirm and orient

Tell the user:
- Session folder: `<work-sessions-repo>/sessions/<session-name>/`
- That the item is now in `work/wip.json` (status `in progress`) — the
  portfolio tracker and the session are linked from the start
- Agentic-sdlc tools worktree: `.../worktrees/agentic-sdlc` (detached, kept in sync by `resume_work_session`)
- Each target repo's worktree path + branch
- Repeat the doctrine compact block (repo north star + engineering defaults)
- Available follow-up commands:
  - `#sync-work.prompt.md` — commit and push at any point
  - `#create-adr.prompt.md` — document a decision
  - `#pause_work_session.prompt.md` — save state and return to main
  - `#stop_work_session.prompt.md` — hard stop, keep branches
  - `#end_work_session.prompt.md` — close out a completed session
  - `#create_work_tree.prompt.md` — add another target repo mid-session
