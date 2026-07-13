---
agent: agent
description: Author a production deployment definition (risk analysis, pre-flight, deployment steps, validation, rollback) for the active session. Writes sessions/<id>/deployments/<name>/DEPLOYMENT.md from the template. Use before any production change; execute it later with #start_guided_deployment.
---

# Define Deployment

Load `.agents/rules/deployments.instructions.md` before drafting — it is not
auto-loaded (see `AGENTS.md` § Integration Schemas) and is the source of truth
for the five artifacts below. Produce the written deployment definition it
requires. **Mandatory before any production change; encouraged for non-prod
deploys too** (same structure, filled briefly for Low-blast-radius non-prod
work). Fills the five artifacts into a
`DEPLOYMENT.md` under the active session. This command only *authors* the plan
— execution is a separate step (`#start_guided_deployment.prompt.md`).

## Steps

### 1. Identify the active session

Read `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo) and filter rows with `Status: active`.
- Exactly one → use it.
- Multiple → list them and ask which session this deployment belongs to.
- None → tell the user to run the `start-work-session` skill first, and stop.

### 2. Gather the deployment details

Ask in sequence (skip any already known from context):

1. **Deployment name** — short slug (e.g. `route53-brand-domains`, `mongodb-cw-monitoring`).
2. **Target environment** — account / region / app, and whether it's **prod or non-prod** (e.g. `cw-prod us-east-1 mk-usp1` (prod), or `cw-test ust1` (non-prod)).
3. **What is changing** — one or two sentences.
4. **Blast radius** — `Low | Medium | High | Critical` (per Operational Safety in `AGENTS.md`). For High/Critical, also ask for a recovery-time estimate.
5. **Related change ticket** — an existing `CHG-####` / URL, or `none` (a production change should have or get one — see `.agents/rules/atlassian.instructions.md`; non-prod usually won't need one).

### 3. Draft all five artifacts

Copy `<work-sessions-repo>/session-template/deployments/DEPLOYMENT.template.md`
to `<work-sessions-repo>/sessions/<session-id>/deployments/<name>/DEPLOYMENT.md`
(create the folder + an `evidence/` subfolder). Fill in the frontmatter, then
draft each of the five sections **concretely** — real commands, real
observables, real rollback actions — using what you know about the change:

1. **Risk Analysis & Blast Radius** — what changes / what doesn't / who's affected / blast radius (+ recovery estimate if High/Critical).
2. **Pre-flight Checks** — read-only checks that hit the real system (correct account/region/profile, `cdk diff`/plan reviewed, no locks or in-flight PR deploys, dependencies healthy, backup if needed). Consult `.agents/rules/aws.instructions.md` for the CDK/env-input preflight rules.
3. **Deployment Steps** — exact ordered commands, each naming the env inputs it consumes and expected output.
4. **Validation Steps** — specific post-change observables with expected results.
5. **Rollback Steps** — exact revert actions, the trigger condition, and recovery-time estimate.

Do not leave any section as a TODO — an incomplete definition cannot be executed. If you genuinely lack the information for a section, ask the user rather than stubbing it.

Set the frontmatter `Status: ready` once all five are filled (leave `draft` if anything is still open).

### 4. Log and report

Append to `<work-sessions-repo>/sessions/<session-id>/WORKLOG.md`:
```
- <YYYY-MM-DD HH:MM> defined deployment <name> (blast radius: <level>) — sessions/<session-id>/deployments/<name>/DEPLOYMENT.md
```

Tell the user:
- The path to the new `DEPLOYMENT.md`
- The blast radius and whether `Status` is `ready` or still `draft`
- That they should review it, then run `#start_guided_deployment.prompt.md` to execute
- For a real production change: the reminder to create/track the change ticket (sections map 1:1)
