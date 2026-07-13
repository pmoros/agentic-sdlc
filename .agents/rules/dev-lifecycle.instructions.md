# Development Lifecycle — Staged Pipeline with Gates

> **Trigger:** read this file before design, implementation, QA, or a gate
> review — loaded explicitly by the `design` skill, `#groom-item`, and the
> `reviewer` agent (Gate A/QA). Not auto-loaded — see `AGENTS.md` §
> Integration Schemas and `02-adrs/0001-tiered-conditional-rule-loading.md`.
> Stage-triggered, so it has no reliable GitHub Copilot `applyTo:` glob;
> Copilot users open this file manually at those points.

The standard, **gated** lifecycle every non-trivial work item flows through —
identical whether a human runs it interactively or the autonomous orchestrator
drives it. It formalizes and *gates* the engineering doctrine (design-first, TDD,
Final Review, guided deployments). Only two points require a human: **Gate A
(design)** and **Gate B (the diff)**; production deploys keep their own gate.

## The pipeline — 7 stages, 2 human gates

| # | Stage | Entry | Exit / gate | Tier |
|---|---|---|---|---|
| 0 | **Planning & Decomposition** | a `ready` item (in `work/wip.json`) | split into sequenced sub-tasks; deps mapped | planner |
| 1 | **Analysis & Discovery** | sub-task picked | problem + **systems/dependencies + real current state** understood; not blocked | planner (+ MCP/CLI reads) |
| 2 | **Design** | discovery done | interface/contract/approach defined (`SPEC.md`) | planner |
| — | **🚪 Gate A — Design Review** | a design exists | **reviewer-agent critique (fresh context) → human approves** before any code | reviewer → human |
| 3 | **Implementation** (TDD) | design approved | red → green → refactor; tests pass | coder |
| 4 | **QA** | implementation green | **fresh-context, argued critique** vs. acceptance criteria + guardrail scan | reviewer/QA (fresh session) |
| — | **🚪 Gate B — Review** (Final Review) | QA passed | **human approves the unified diff; push/PR/merge here** | human |
| 5 | **Deploy** | change merged; a deployment definition exists | guided deploy; **production is gated** (see `deployments.instructions.md`) | operator + human gate |

A stage that fails loops **back** (QA fail → Implementation; discovery finds a
blocker → park the item) rather than advancing. Small/trivial changes may collapse
stages, but **never skip a gate**.

## Stage 1 — Systems & Dependency Discovery (mandatory before design)

Establish the **real world**, not assumptions — read-only reconnaissance via
MCP/CLI **before** designing:

- **Dependencies** — does this change depend on, or force, a change in another
  system/service? Any upstream/downstream consumers to coordinate?
- **Existing work** — is there **already an open PR / issue / branch** in GitHub
  for this? Search first; don't duplicate or collide.
- **Real current state** — query the target systems **read-only, now** (e.g.
  `aws … --query` for actual AWS state, the live Jira ticket, branch/ruleset
  state) rather than reasoning from stale memory.
- **Constraints** — branch-naming/signing rulesets, deploy windows, blast radius.

**Exit:** a short dependency/state report. If it surfaces a blocker ("depends on
system A", "a PR already exists"), **park the item with that finding** instead of
proceeding to design.

## Shared critique rubric (Gate-A review *and* QA)

Both are **fresh-context** (no anchoring on the author's rationale) and produce an
**argued** critique — never a bare pass/fail. Organize findings under:

1. **Architectural characteristics** — the "-ilities": performance, scalability,
   security, reliability/availability, maintainability, cost, operability,
   simplicity (Well-Architected / architecturally-significant-requirements lens).
2. **Functional requirements** — does it actually meet the stated acceptance
   criteria and intended behavior?
3. **Best / good practices** — idioms, patterns, and this repo's doctrine (TDD,
   KIS, design-first, conventions, secrets hygiene).

Each finding carries: **an argument** (why it matters + the trade-off), a
**severity**, and a **reference** (vendor doc, standard, or in-repo precedent).
The reviewer that authored the work must not be the reviewer that critiques it —
QA/design-review run in a fresh context (a separate agent/session).

## Autonomy mapping (for the orchestrator)

- Task type → stage → tier: `planning/discovery/design → planner (Opus)`;
  `implement/fix/test → coder (Sonnet)`; `qa/verify → reviewer (Sonnet, fresh)`;
  `design-review/review → reviewer (Opus, fresh)`.
- Gates A and B and every external write (push/PR/merge/cloud/deploy) are
  human-gated per the autonomy policy; advancing a gate without approval is a
  guardrail violation (a hard-zero metric).
