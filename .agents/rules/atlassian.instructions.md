# Atlassian Integration — Structural Schema (Template)

> **Trigger:** read this file before any Jira or Confluence operation (read,
> create, update, transition, comment). Not auto-loaded — see `AGENTS.md` §
> Integration Schemas and `02-adrs/0001-tiered-conditional-rule-loading.md`.
> Operation-triggered, so it has no reliable GitHub Copilot `applyTo:` glob;
> Copilot users open this file manually before Jira/Confluence work.

This file is the **operational source of truth** for Jira/Confluence work
driven from this repo. It ships with placeholder projects — replace the
Quick Reference table and the per-project sections with your own org's
projects, keys, custom fields, and workflow states before relying on it.
Everything else (formatting gotchas, MCP tool priority, pre-flight
discipline) is reusable as-is.

## Quick Reference

**Org:** forgestop · **Atlassian site:** `forgestop.atlassian.net` (single
Cloud site for both Jira and Confluence, served by the `atlassian` remote MCP
server — see `AGENTS.md` § MCP Setup).

### Jira projects

| Project | Key | Jira Instance | Issue Types |
|---|---|---|---|
| INFRA & OPS | `IO` | `forgestop.atlassian.net` | Task, Bug, Story, Epic, Sub-task, Spike, Critical Incident |
| DASHBOARD | `DA` | `forgestop.atlassian.net` | Task, Bug, Story, Epic, Sub-task, Spike |
| BATCHMAKER | `FB` | `forgestop.atlassian.net` | Task, Bug, Story, Epic, Sub-task, Spike |
| AUTH APP | `AA` | `forgestop.atlassian.net` | Task, Bug, Story, Epic, Sub-task, Spike |

`cloudId` = `2af0b82e-3b5c-4465-82e3-7e6a7d2ad596`. **Other projects** on the same site (client/other): DIA (Diageo India), IFA, JNX, MAN, NEO, OC, PI.

**Project types & workflows** (discovered ADH-006; IO transitions verified 2026-08-16):

- **IO — INFRA & OPS** (software, team-managed) — owns infra + platform CI/CD tooling + SOC 2 governance; unique **Critical Incident** issue type. Workflow: `To Do → In Progress → IN REVIEW → IN TESTING → READY TO DEPLOY → Done` (+ `Backlog`, `CANCELED`). No direct In Progress→Done — step through each state. Transition IDs: Backlog=`2`, In Progress=`3`, IN REVIEW=`4`, IN TESTING (transition name "QA")=`5`, READY TO DEPLOY ("Ready")=`6`, Done ("End")=`7`, CANCELED=`8`. Transition *names* differ from target *status* names — match on the transition's `to.name`, and re-fetch transitions after each hop (most non-global ones are only offered from the adjacent state).
- **DA — DASHBOARD** (software, team-managed) — largest/most active project; backlog for the `forgestop-platform` monorepo. Migrated 31 Jul 2025 (legacy keys `FD`/`FE` still appear on old branches). Workflow: `BACKLOG / To Do → In Progress → IN REVIEW → IN TESTING → Done` (+ `Canceled`). Transition IDs not fully enumerated — call `getTransitionsForJiraIssue` before transitioning.
- **FB — BATCHMAKER** (**business**-type project → weaker native dev-tool integration than the software projects). Workflow: `BACKLOG → To Do → In Progress → IN REVIEW → Done` (+ `CANCELED`; no IN TESTING observed).

**Jira ↔ GitHub linkage:** convention-only — branches `<type>/<KEY-nnn>/<slug>`, PR titles `type(scope): … [KEY]`. No Smart Commits, no `Refs:` footers; not enforced (governance-as-IaC tracked under IO-89 / IO-260).

### Confluence spaces

Cross-org, ask-at-session-start/close candidates (ADH-008 Phase 6 — see the
`start-work-session` skill and `#end_work_session.prompt.md`'s Confluence
steps):

| Space | Key | Confluence Instance |
|---|---|---|
| Software Development | `SD` | `forgestop.atlassian.net` |
| AI & Operation Standards & Guides | `AASG` | `forgestop.atlassian.net` |
| Product | `Product` | `forgestop.atlassian.net` |
| Operations | `BO` | `forgestop.atlassian.net` |

**Other spaces** — client-specific knowledge bases, offer when the session's
goal names that client (several map 1:1 to the Jira "Other projects" list
above): `IFA` (IFA Celtics), `PIC` (Piccadily), `OCU` (Ocusoft), `NEO`
(Neolpharma), `MAN` (Mankind Pharma), `JNX` (JNX Sports), `DIA` (Diageo
India), `CSK` (Customer Support Knowledge).

> **Confluence fully seeded** (2026-08-18, via `getConfluenceSpaces`). Jira
> project keys/issue types/custom fields below are still `TBD` — capture on
> first connect, same procedure.

---

## Shared — Language Policy

All content written to Jira and Confluence — summaries, descriptions,
comments, resolution notes, attachments — must be in **English**, regardless
of the language used in conversation with the user.

---

## Shared — Confluence Wiki Discovery (CQL)

Used by `start-work-session`'s and `#end_work_session.prompt.md`'s
Confluence steps (ADH-008 Phase 6) — read-only, autonomous, never a write.

- **Scope to the space(s) the user named** from the table above (or an
  "Other spaces" one). Never search unscoped across every space — too noisy,
  and pulls in personal/client spaces the user didn't ask about.
- **Query shape:** `space in (<key1>, <key2>) AND type = page AND text ~
  "<keyword1> <keyword2> ..."`. Keywords: the ticket key if there is one
  (search it standalone too — `text ~ "PROJ-1234"` — since a linked ticket
  key is a stronger signal than goal-word overlap), plus 2-4 significant
  words from the session goal (drop stopwords/type-prefixes like `[feat]`).
- **Surface candidates as title + link**, ranked as the tool returns them
  (relevance-ordered); don't re-rank. Cap what you show at a reasonable
  number (~5-8) — don't dump every match.
- **The user decides what's relevant**, every time — never auto-link a page
  without it being explicitly picked, even a single unambiguous-looking
  result.
- **No space named ⇒ no search.** Don't fall back to guessing a space.

---

## Shared — Description Formatting

Jira Cloud uses **ADF (Atlassian Document Format)**. Most Jira MCP servers
auto-convert markdown to correct Jira syntax. **Always write in markdown —
never raw Jira wiki markup.**

### What NOT to write
- `{{resource-name}}` — renders literally
- `[label|https://url]` — wiki link syntax, renders as literal text
- `||*Header*||` — some MCPs inflate the column count
- `h3. Title` — renders literally
- `+text+` in table cells — `+` is stripped by some renderers

### Correct markdown equivalents
- Hyperlinks: `[label](https://url)`
- Bold: `**bold**`, italic: `_italic_`
- Tables: `| col |` with `|---|` separators — column count must match across header, separator, and all data rows
- Avoid `+`, `*`, `{`, `}`, `|` in table cell content

---

## Shared — Known MCP Quirks

Use this section as a running log of quirks discovered for your Jira
instance and MCP server (field encoding bugs, fields that silently ignore
certain value shapes, link-type names that don't match the UI label, etc.).
Two illustrative examples of the *kind* of thing that belongs here:

### `&` in summary field
Some Jira create-issue tools HTML-encode `&` as `&amp;` in the summary. If
you see this, immediately call the update-issue tool with the plain `&` to
fix the title.

### `priority` placement
Some MCP servers require `priority` to be passed inside an
`additional_fields` / `additional_fields`-style container rather than as a
top-level field:
```json
{ "priority": { "name": "Medium" } }
```
Check your Jira instance's allowed priority values (some orgs restrict the
standard Low/Medium/High set) and document them here.

### Issue link type names
Link type names in the UI don't always match the API name exactly (trailing
spaces, different casing). If unsure, call the link-types-list tool first
and use the `name` value verbatim rather than guessing.

---

## Tool Priority — Atlassian Operations

If more than one Atlassian MCP server is configured, document the tradeoffs
here — for example:

| Server | Best for | NOT supported |
|---|---|---|
| _MCP A_ | Jira/Confluence attachments, complex field updates | Rich Confluence HTML |
| _MCP B_ | Jira search (JQL), create/edit/transition issues, rich Confluence HTML | File attachments |
| Atlassian REST via `curl` / `fetch` | Last resort — only if the tool is genuinely absent after discovery | — |

**Fallback trigger:** Only fall back if the required tool is genuinely
unavailable. Never fall back because a tool returned an error — fix the
parameters and retry.

### Tool discovery rule

Do not choose Atlassian tools by MCP server name alone — the server name in
`.mcp.json` does not guarantee the exact runtime tool names exposed to
the agent. When loading Atlassian tools, search by the operation you need
(read issue, create issue, search, comment, transition), not by an assumed
namespace prefix. Use the exact tool name returned by tool discovery.

**Attachment requirement:** if your Atlassian MCP server runs in Docker, it
typically needs a volume mount exposing the contributor's home directory
(e.g. `"-v", "/home/<user>:/home/<user>:ro"`) or host-path attachments will
fail with "File not found".

### Mandatory pre-flight before any Jira write

1. **Fetch before write** — always read the current issue before any update. Prefer a direct issue-read operation first. If a direct read tool isn't exposed, fall back to an exact-key JQL/search query (`key = ABC-123`). Capture the full current `description` and merge it with the new content. Never discard existing description text unless explicitly instructed.
2. **Exhaust MCP read paths before fallback** — before declaring Jira read unavailable, check every available MCP read path. Only fall back to CLI or REST if all are genuinely unavailable after discovery.
3. **Call the tool — do not narrate it** — never describe what you _would_ do and skip the actual tool call. Every write operation (update, comment, transition) must produce a real tool response before you tell the user it succeeded.

### Ticket creation execution rule

When the required project, issue type, summary, description, and required
custom fields are already documented in this file, **create the ticket
directly** with the appropriate Jira create tool — don't detour through
subagents or broad tool discovery once a valid create tool is known.

Do **not** delay creation by:
- launching a subagent for a simple, well-specified create
- doing broad tool discovery after the correct create tool is already available
- using generic/semantic search to infer field values that are already documented in this file
- blocking on assignee resolution when the ticket can be created first and assigned immediately afterwards

If a reusable Jira gap is discovered while working from this repo:
- update this instruction file when the gap is a stable process rule
- or store it in repo-scoped memory when it is only a workspace-level reminder

Do **not** promote ticket-specific, worktree-specific, or session-specific
Jira behavior into global memory.

### Verify the response — never assume success

After every tool call, inspect the response:
- Look for a success message (e.g. `"Issue updated successfully"`)
- If the response contains an error or is empty, surface it to the user and stop — **do not claim the operation succeeded**
- A hallucinated "Done!" without a tool response is a critical failure

---

## Project Template — copy this section per project

Duplicate this section for each Jira project in the Quick Reference table
above, replacing the placeholders.

### `PROJ` — Example Project Name

**Project Info**
- Jira instance: `yourcompany.atlassian.net`
- Project key: `PROJ`
- Any always-required custom field (e.g. team/portfolio): `customfield_XXXXX` → `"<value>"`

**Workflow States**

`Backlog` → `In Progress` → `Review` → `Done`

> Note any workflow automations here (auto-assignment, auto-transition on
> certain events, round-robin reassignment, etc.) — these are easy to be
> surprised by and expensive to rediscover.

**Transition IDs**

| ID | Transition | From state |
|---|---|---|
| `<id>` | `<name>` | `<state>` |

> Always call the get-transitions tool before transitioning instead of
> assuming the current state — it can change unexpectedly (e.g. an
> attachment upload can trigger an automation that moves the issue).

**Custom Fields**

| Field ID | Field Name | Notes |
|---|---|---|
| `customfield_XXXXX` | `<name>` | `<allowed values / notes>` |

**Ticket Template**

A well-formed ticket for this project includes:
- **Summary**: concise, imperative description
- **Description**: context, motivation, acceptance criteria (markdown)
- **Issue Type**: `<Story \| Task \| Bug \| Spike>`
- **Assignee**: default to the person making the request unless they say otherwise

---

## Change-Management Ticket Template (optional)

If your org runs a formal change-management process through Jira (a
"Standard Change Request" style project), this six-section description
template maps cleanly onto a deployment definition's five artifacts (see
`.agents/rules/deployments.instructions.md`):

```markdown
## Description
<What changes, why it is needed, and any related tickets/PRs.>

## Implementation Details
<Numbered deploy steps — tools, commands, sequence, estimated duration.>

## Rollback Details
<How to revert if something goes wrong — steps, commands, estimated time.>

## Verification Details
<Commands or checks to confirm the change was applied correctly.>

## Affected Resources
<Environment names, resource identifiers, etc.>

## Resolution Notes
<To be completed after the change is deployed.>
```

Document your change project's required custom fields, allowed values, and
transition IDs using the same shape as the Project Template above.
