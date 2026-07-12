# Runbooks

Guided, step-by-step operational procedures for multi-step SOPs you want an
agent (or a human) to execute consistently — the kind of thing that's too
long-lived and too specific to live inline in a `.agents/commands/*.prompt.md`
file, but still needs to be repeatable and reviewable.

This folder is empty in the generic framework on purpose. Runbooks tend to be
tightly coupled to your org's actual infrastructure and products (e.g. "how
we rotate a database credential", "how we rename a customer-facing resource",
"how we right-size a storage volume") — write your own here as you need them.

## When to add a runbook here vs. elsewhere

| Use | Location |
|---|---|
| One-off atomic operation, reusable across any repo | `.agents/commands/<name>.prompt.md` |
| Multi-step SOP tied to specific infrastructure/product, with its own scripts/tests | `runbooks/<name>/` |
| Org-specific automation an agent should discover and invoke by name | `.agents/skills/<name>/SKILL.md` (can shell out to a runbook here) |

## Suggested shape for a runbook folder

```
runbooks/<name>/
  README.md       — what this runbook does, when to use it, prerequisites
  RUNBOOK.md       — the actual step-by-step procedure
  <scripts>        — any scripts the procedure shells out to, each with tests
                      per the Script Testing Standard in
                      .agents/rules/engineering.instructions.md
```

## Index

| Runbook | Purpose |
|---|---|
| _(none yet)_ | |
