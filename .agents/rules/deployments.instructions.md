# Deployment Policy

> **Trigger:** read this file before authoring or executing a deployment
> definition (`#define_deployment`, `#start_guided_deployment`) — i.e.
> before any change to a production or customer-facing environment. Not
> auto-loaded — see `AGENTS.md` § Integration Schemas and
> `02-adrs/0001-tiered-conditional-rule-loading.md`. The deployment artifacts
> this file governs live in the sibling `work-sessions` repo, so it has no
> reliable GitHub Copilot `applyTo:` glob from this repo; Copilot users open
> this file manually before deployment work.

Any operation that **changes a production environment** — deploy/apply/migrate/
scale/DNS/route/config change against production cloud infra, managed
services, databases, or customer-facing systems — MUST have a written
deployment definition before execution. No production change is run ad-hoc.

The same deployment-definition structure is also **encouraged for non-prod
deployments** (dev-account experiments, staging pushes, test-account CDK
apps) so the session's `deployments/` folder is a complete record of what was
deployed and how, regardless of environment — not just production. This is
encouraged practice, not a hard gate: a non-prod, Low-blast-radius deploy can
fill out the five sections briefly rather than skipping the definition
entirely.

This rule operationalizes the three-phase write protocol and blast-radius
scale in `AGENTS.md` → Framework Rules → Operational Safety. It does not
replace them: guarded mode, destructive-operation double-confirmation, and the
per-step approval protocol still apply.

## Scope — when a deployment definition is required

**Mandatory** for any change to a **production** or **customer-facing**
environment. If unsure whether a target counts as production, treat it as
production.

**Encouraged, not required**, for non-prod deployments and anything
High/Critical blast radius regardless of environment — use the same
`DEPLOYMENT.md` structure so there's a durable record, but a missing
definition doesn't block execution the way it does for production.

**Not applicable** to localhost/dev-sandbox work (see Flex Mode) or read-only
queries — there's no deployment to record.

## The five mandatory artifacts

Every deployment definition captures all five. They map onto the
change-management ticket template in `.agents/rules/atlassian.instructions.md`,
so a definition can seed a change-management ticket directly.

| Artifact | Must answer | Maps to change-ticket section |
|---|---|---|
| **1. Risk analysis & blast radius** | What changes, what does NOT, who/what is affected, blast radius (Low/Medium/High/Critical per Operational Safety), and — for High/Critical — recovery time estimate | Description |
| **2. Pre-flight checks** | Concrete read-only checks proving it's safe to start: correct account/region/profile, dry-run/plan output reviewed, no active locks or in-flight deploys, dependencies healthy, backup taken if needed | Implementation Details (preconditions) |
| **3. Deployment steps** | The exact ordered commands/actions, each with the environment inputs it consumes (profile, environment ID, branch/version selector, etc.) and expected output | Implementation Details |
| **4. Validation steps** | Post-change checks proving success: specific commands/observables (curl, dig, CloudWatch metric, record read-back) with expected results — not "looks fine" | Verification Details |
| **5. Rollback steps** | The exact ordered actions to revert, when to trigger them, and the recovery-time estimate | Rollback Details |

A definition with any of the five empty or left as a TODO is **not valid** and
must not be executed.

## Workflow

1. **Author** the definition with `#define_deployment.prompt.md` — it writes
   `sessions/<id>/deployments/<name>/DEPLOYMENT.md` from the template.
2. **Review** it (the human owner reads and approves the plan as written).
3. **Execute** with `#start_guided_deployment.prompt.md` — it refuses to start
   if any of the five artifacts is empty, then walks pre-flight → deployment →
   validation with an approval gate before the first production-mutating step,
   recording evidence under `deployments/<name>/evidence/`. On any failure it
   surfaces the rollback steps immediately.
4. For a real production change, also create/track a change-management
   ticket (see `.agents/rules/atlassian.instructions.md`); the DEPLOYMENT.md
   sections copy across 1:1.

## Execution guardrails (in addition to Operational Safety)

- Never batch multiple production-mutating steps behind a single approval —
  gate each mutating step.
- Treat environment-selecting inputs (AWS profile, environment ID, app name,
  branch/version selector, etc.) as deliberate inputs, not defaults (see
  `.agents/rules/aws.instructions.md`). If a change expected to be in-place
  shows full resource creation in the diff, stop and re-check before executing.
- Record every executed step's real output to `evidence/` and append a
  timestamped line to the session `WORKLOG.md`.
- A dry run that only reads a local file is not a pre-flight — pre-flight must
  hit the real system read-only.
