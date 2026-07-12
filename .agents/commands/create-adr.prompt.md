---
agent: agent
description: Guided creation of an Architecture Decision Record (ADR) in the appropriate project-level folder.
---

# Create ADR

## Step 1 — Locate the ADR folder

Search the repository for an existing ADR folder, starting from the current working directory and checking common conventions:
- `docs/adr/`
- `docs/decisions/`
- `docs/architecture/decisions/`
- `architecture/decision-records/`
- `<project>/docs/adr/`

If working inside a monorepo (multiple top-level packages or services), scope the search to the nearest project folder — **never place ADRs at the repo root** for a monorepo.

If no ADR folder is found:
- Ask the user: "No ADR folder found. Where would you like to create one? (suggest the most likely path based on project structure)"
- Wait for confirmation before creating the folder.

## Step 2 — Determine the next ADR number

List the files in the ADR folder and identify the highest existing ADR number. The new ADR will be `ADR-<NNN>` (zero-padded to 3 digits).

If the folder is empty or new, start at `ADR-001`.

## Step 3 — Gather the ADR content

Ask the user the following questions (can be answered in one message):

1. **Title**: What is a short title for this decision? (e.g. "Use PostgreSQL for primary storage")
2. **Problem statement**: What problem or need is this decision addressing?
3. **Options considered**: What are the alternatives? (at least 2 required — push back if only 1 is given)
4. **Decision**: Which option was chosen and why?
5. **Consequences**: What are the positive outcomes? What are the trade-offs or risks?
6. **Status**: `proposed` | `accepted` | `deprecated` | `superseded` (default: `accepted`)

If a session is active, check its `CONTEXT.md` in `<work-sessions-repo>/sessions/<session-id>/` (sibling `../work-sessions`) for context that may help pre-fill the problem statement or decision. For a decision scoped to the work itself (not a target repo's architecture), prefer the session's own `adrs/` folder over a project-level ADR folder.

## Step 4 — Draft the ADR

Generate the ADR using this template:

```markdown
# ADR-<NNN>: <Title>

**Date:** <YYYY-MM-DD>
**Status:** <status>

## Context

<problem statement>

## Options Considered

### Option 1: <label>
<brief description, pros, cons>

### Option 2: <label>
<brief description, pros, cons>

<!-- add more options as needed -->

## Decision

<chosen option and rationale>

## Consequences

**Positive:**
- <outcome 1>

**Negative / Trade-offs:**
- <trade-off 1>
```

Show the full draft to the user and ask: "Does this look right? I'll write the file once you confirm."

## Step 5 — Write the file

After user approval:
- Write the ADR to `<adr-folder>/ADR-<NNN>-<kebab-title>.md`
- Confirm the path to the user

## Step 6 — Update session file

If a session is active, append to its `CONTEXT.md` `## Activity log` (in `<work-sessions-repo>/sessions/<session-id>/`):

```
- <YYYY-MM-DD HH:MM> recorded ADR-<NNN>: <Title> — <adr-folder>/ADR-<NNN>-<kebab-title>.md
```

Confirm to the user: "ADR-<NNN> written and session activity log updated."
