---
name: design
description: >
  Design-first for a piece of work before implementation: define the interface,
  contract, schema, or approach and capture it as the session SPEC. Use for
  "design this before we build it", "let's spec this out", "what's the approach
  for <item>", "define the interface/schema first", or when a groomed item is
  about to be picked up and needs a design. Enforces the Design-first
  engineering doctrine and produces a reviewable artifact.
---

# Design

Produce a design/approach for a piece of work **before** any implementation, per
the Design-first doctrine in `.agents/rules/engineering.instructions.md`
(define the interface, contract, or schema first; propose and get approval
before generating implementation). The output is a reviewable SPEC, not code.

State and session files live in the sibling `work-sessions` repo
(`<work>` = `../work-sessions`). If a session is active for this
work, the design lands in that session's `SPEC.md`; otherwise it's a standalone
design doc for a backlog item.

## When to use

- A groomed, `ready` item is about to be picked up and involves a non-trivial
  interface, data model, API, or infra change.
- The user asks to spec/design something before building.

For architectural decisions with lasting cross-repo impact, use `#create-adr`
instead (or alongside) — an ADR records *the decision*; this skill produces
*the design*.

## Steps

### 1. Anchor to the item and its acceptance criteria

Identify the work item and read its acceptance criteria and test scenarios
(from the backlog item and/or the Jira ticket). If those aren't clear yet, the
item isn't ready — run `#groom-item` first. A design must satisfy explicit AC.

### 2. Clarify constraints

Surface the constraints that shape the design before proposing one: target
environment, existing patterns in the repo, relevant Well-Architected pillars,
performance/cost/security requirements, and any repo doctrine
(`.copilot-doctrine.md`). Ask when a constraint is material and unknown — don't
assume.

### 3. Define the design (interface/contract/schema first)

Draft the design at the right altitude for the change:
- **API / service work** — the typed interface, OpenAPI/protobuf shape, or
  contract, before handler logic.
- **Data model work** — the schema / domain model, before persistence rules.
- **Infra / CDK work** — the resource shape, inputs, and blast radius (tie to
  `.agents/rules/deployments.instructions.md` if it touches a real environment).

Include: the approach, at least one considered alternative and why it lost,
the interface/schema itself, and the `Given / When / Then` scenarios the design
must satisfy (these become the tests, per TDD/BDD).

### 4. Capture as a SPEC

Write the design to the session's `SPEC.md` (`<work>/sessions/<id>/SPEC.md`) if
a session exists, or to a standalone doc otherwise. Structure: Context & AC →
Constraints → Approach (with alternatives) → Interface/Schema → Test scenarios
→ Open questions / risks.

### 5. Review gate

Show the full design and ask for explicit approval before any implementation.
Per the doctrine, do not generate implementation code until the design is
agreed. If there are open questions, list them and get answers rather than
guessing.
