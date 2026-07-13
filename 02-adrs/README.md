# Architecture Decision Records

This folder contains Architecture Decision Records (ADRs) for this agentic SDLC toolbox.

## What is an ADR?

An ADR is a short document that captures a significant architectural or process decision, its context, and its consequences. ADRs are immutable once accepted — superseded decisions get a new ADR that references the old one.

## Status Lifecycle

```
Draft → Proposed → Accepted → Superseded / Deprecated
```

| Status | Meaning |
|---|---|
| `Draft` | Being authored, not yet ready for review |
| `Proposed` | Ready for review and discussion |
| `Accepted` | Decision is in effect |
| `Superseded` | Replaced by a newer ADR (link provided) |
| `Deprecated` | No longer applicable; not replaced |

## Naming Convention

```
NNNN-short-lowercase-title.md
```

- `NNNN` — zero-padded four-digit sequence number (e.g. `0001`)
- Title — kebab-case, imperative mood, max ~60 characters
- Example: `0001-use-conventional-commits-across-all-repos.md`

## ADR Template

Use `#create-adr.prompt.md` via the Copilot agent to create a new ADR interactively, or copy the template below:

```markdown
# NNNN — Title

| Field | Value |
|---|---|
| **Status** | Draft |
| **Date** | YYYY-MM-DD |
| **Deciders** | |
| **Tags** | |

## Context

<!-- What is the issue or situation that motivated this decision? -->

## Decision

<!-- What was decided? State it clearly and concisely. -->

## Consequences

### Positive
-

### Negative / Trade-offs
-

### Neutral
-

## Alternatives Considered

<!-- What other options were evaluated, and why were they rejected? -->

## References

<!-- Links to relevant documents, issues, or prior ADRs. -->
```

## Index

| ID | Title | Status | Date |
|---|---|---|---|
| [0001](0001-tiered-conditional-rule-loading.md) | Tiered, Conditional Loading of Integration & Lifecycle Rules | Accepted | 2026-07-13 |
