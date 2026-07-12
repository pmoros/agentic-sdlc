---
agent: agent
description: Execute a deployment definition step-by-step — pre-flight, gated deployment steps, validation — recording evidence, with rollback surfaced on failure. Consumes a DEPLOYMENT.md authored by #define_deployment. Use to run a defined deployment (prod or non-prod) safely; production-mutating steps stay gated per step.
---

# Start Guided Deployment

Execute a deployment defined by `#define_deployment.prompt.md`, enforcing
`.agents/rules/deployments.instructions.md` and the Operational Safety
three-phase protocol / approval protocol in `AGENTS.md`.

## Steps

### 1. Locate the deployment definition

Identify the active session (`<work-sessions-repo>/SESSIONS_STATE.md`, `Status: active`).
List `sessions/<session-id>/deployments/*/DEPLOYMENT.md`:
- Exactly one → use it.
- Multiple → show name + blast radius + `Status` from frontmatter, ask which to run.
- None → tell the user to run `#define_deployment.prompt.md` first, and stop.

### 2. Validate completeness (hard gate)

Read the `DEPLOYMENT.md`. **Refuse to proceed** if any of the five sections
(Risk Analysis & Blast Radius, Pre-flight Checks, Deployment Steps, Validation
Steps, Rollback Steps) is empty, still contains template placeholder text, or
is left as a TODO. If incomplete:
> "This deployment definition is incomplete (`<section>` is empty). Run `#define_deployment.prompt.md` to finish it before executing."
Then stop.

Show the user the risk analysis + blast radius and the full ordered plan, and
**wait for explicit approval to begin**.

### 3. Pre-flight (read-only)

Run each Pre-flight check. These are read-only and may run without per-step
approval, but show each command and its output. If any check fails or returns
something unexpected (e.g. wrong account, a diff showing resource creation
where an in-place update was expected — see `.agents/rules/aws.instructions.md`),
**stop and surface it** — do not continue to deployment steps. Record output
under `deployments/<name>/evidence/preflight-<YYYYMMDD-HHmmss>.txt`.

### 4. Deployment steps (gated)

Before the **first production-mutating step**, restate the blast radius and get
explicit approval (a second, distinct confirmation for Critical/destructive
changes, per Operational Safety). Then run steps in order:
- Show each command before running it.
- Gate each production-mutating step on its own approval — never batch mutating steps behind one approval.
- Capture each step's real output to `deployments/<name>/evidence/step-<n>-<YYYYMMDD-HHmmss>.txt`.
- If any step fails, **stop immediately** and go to step 6 (rollback).

### 5. Validation

Run each Validation step; compare actual vs. expected. Record output to
`deployments/<name>/evidence/validation-<YYYYMMDD-HHmmss>.txt`. If validation
fails, treat it as a failed deployment → step 6.

### 6. Rollback (on any failure)

If a deployment or validation step failed, immediately surface the Rollback
Steps from the definition and ask the user whether to execute them now. Run
them with the same per-step gating and evidence capture. Do not silently leave
a half-applied production change.

### 7. Record outcome

Append to `<work-sessions-repo>/sessions/<session-id>/WORKLOG.md`:
```
- <YYYY-MM-DD HH:MM> guided deployment <name> — <succeeded | failed at step N, rolled back | rolled back>
```
Update the `DEPLOYMENT.md` frontmatter `Status` to `deployed` or `rolled-back`.
If a change ticket is linked, remind the user to attach the evidence and add resolution
notes before transitioning it to Complete (per `.agents/rules/atlassian.instructions.md`).

Tell the user the outcome, where the evidence is, and — on success — the
validation results that confirm it.
