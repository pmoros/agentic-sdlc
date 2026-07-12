# agentic-sdlc

A generic, portable **agentic SDLC toolbox**: commands, rules, skills, and
scripts that let an AI coding agent (Claude Code, GitHub Copilot, or
similar) run real work sessions — from picking up a ticket, through a
git-worktree-isolated implementation, to opening a PR — with guardrails
around external writes, deployments, and secrets baked in.

This repo is one half of a two-repo framework:

| Repo | Role |
|---|---|
| **`agentic-sdlc`** (this repo) | The **toolbox** — commands/rules/skills/scripts. Read-only, versioned, shared across everyone using the framework. Holds **no session state**, not even gitignored. |
| **`work-sessions`** (sibling, from [`work-sessions-template`](../work-sessions-template)) | The **state** — your personal backlog, WIP, session history, plans, and retros. Instantiated per person from the template repo, private, and commits everything so it survives across machines and time. |

The split exists so the *process* (this repo) can be shared and improved
without ever touching anyone's *private work data* (the sibling repo).

## Purpose

This repository is the **toolbox**: scripts, runbooks, and the `.agents/`
commands/rules/skills used to run work sessions. It does not contain
application code, and it holds **no session state** — not even gitignored.
All session state (backlog, active/paused/done sessions, plans, decisions,
worktrees) lives in the sibling `work-sessions` repo, which commits
everything so it survives across machines and time.

- Architecture Decision Records (ADRs) for this repo's own tooling/process
- Shared prompts, skills, and Copilot/Claude customisations
- `scripts/` — deterministic automation the commands above shell out to
- Archived historical documents

## Getting started

1. **Set up the sibling state repo.** Create your own `work-sessions` repo from
   [`work-sessions-template`](../work-sessions-template) (see that repo's
   README) and clone it next to this one:
   ```
   repos/
     agentic-sdlc/        (this repo)
     work-sessions/       (your private instance, from the template)
     <your other repos>/
   ```
2. **Fill in the integration templates.** `.agents/rules/atlassian.instructions.md`
   and `.agents/rules/aws.instructions.md` ship with placeholder projects/values —
   replace them with your org's actual Jira projects, custom fields, AWS
   profile conventions, etc. Run `#configure-integrations.prompt.md` for a
   guided pass, or edit the files directly.
3. **Set up local MCP config** (optional, for Jira/Confluence/AWS/GitHub tool
   access): `cp .vscode/mcp.example.json .vscode/mcp.json`, then restart your
   editor — see `AGENTS.md` → MCP Setup.
4. **Start a session:** invoke the `start-work-session` skill (or `#start_work_session`)
   from your agent. It creates a session folder in `work-sessions`, registers
   it, and sets up worktrees for this repo plus any target repos.

## Security checks & CI

This repo pins its dev/CI tooling with [mise](https://mise.jdx.dev) — run
`mise trust && mise install` once to fetch the exact `gitleaks` / `shellcheck`
/ `actionlint` versions declared in `.mise.toml`. Run all checks locally with:

```bash
scripts/security-check.sh          # secrets + shell lint + workflow lint
scripts/security-check.sh secrets  # just the gitleaks secret scan
```

`.github/workflows/ci.yml` runs the same checks (via the same pinned
versions, installed by the `jdx/mise-action` GitHub Action) plus the
`scripts/tests/` suite on every push and PR — a clean local run should never
disagree with CI.

## Reference Repo Policy

Every repo under `repos/` — including this one — is a
**read-only source of truth**: always checked out on its default branch,
always kept in sync with `origin`, and never edited directly. All real work
happens only in a worktree created under a session's `worktrees/` folder in
`work-sessions`. See `docs/create-worktree.md` and the
Reference Repo Policy section of `AGENTS.md`.

Every session gets a mandatory worktree of this repo (detached, on the
default branch, kept in sync) at `worktrees/agentic-sdlc/` in its session
folder, so its tools are available without ever touching this repo's own
checkout directly.

## VS Code Multi-Root Workspace

The recommended way to browse this repo alongside its sibling repos under
`repos/` is a VS Code **multi-root workspace**.

### Setup (one time per developer)

1. Copy the example workspace file to create your personal one:
   ```sh
   cp agentic-sdlc.code-workspace.example \
      agentic-sdlc.code-workspace
   ```
2. Edit the copy — remove sibling repos you aren't using, add any you need.
3. Open the workspace file in VS Code: **File → Open Workspace from File…**

The actual `.code-workspace` file is gitignored (paths are developer-specific). The `.example` file is committed as the canonical template.

Session worktrees are not tracked in this workspace file — they live in
`work-sessions`, which has its own workspace file for that
purpose.

## Repository Layout

| Folder | Purpose |
|---|---|
| `.agents/agents/` | Specialist subagent definitions (source of truth), symlinked into `.claude/agents/` |
| `.agents/commands/` | Command prompts (source of truth), symlinked into `.claude/commands/` and `.github/prompts/` |
| `.agents/rules/` | Auto-loaded rules — integration schemas (Atlassian, AWS, GitHub), engineering doctrine, production-deployment policy, session-state maintenance — symlinked into `.github/instructions/` |
| `.agents/skills/` | Auto-discovered skills (session orchestration, planning, design), symlinked into `.claude/skills/` |
| `scripts/` | Deterministic automation the commands above shell out to (worktree creation, session init, tmux, security checks) — see `scripts/README.md` |
| `runbooks/` | Guided operational procedures for org-specific SOPs — empty by default, see `runbooks/README.md` |
| `.github/workflows/` | CI — secret scan + shell/workflow lint + script tests on every push/PR |
| `.mise.toml` | Pinned versions of the tools CI and `scripts/security-check.sh` use |
| `docs/` | Reference documentation (e.g. the worktree/CoW deep-dive) |
| `02-adrs/` | Architecture Decision Records for this repo's own tooling/process |
| `01-scratchpad/` | Drafts and experiments |
| `99-archive/` | Superseded or historical documents |

## ADRs

Architectural decisions that affect the agentic SDLC process or the conventions used across repos are recorded in [`02-adrs/`](02-adrs/README.md). See that folder for the index and authoring guidelines.

## Skills

Commands live in [`.agents/commands/`](.agents/commands/) (symlinked into
`.claude/commands/` and `.github/prompts/`) and skills live in
[`.agents/skills/`](.agents/skills/). Invoke by name or natural-language
trigger, or with `#<name>.prompt.md` for commands.

| Command / Skill | Purpose |
|---|---|
| `start-work-session` *(skill)* | Start a new work session — orchestrates `initialize_work_session_folder` + `create_work_tree` per target repo |
| `#initialize_work_session_folder` | Atomic: gather session details, create the session folder in `work-sessions`, set up the mandatory `worktrees/agentic-sdlc` worktree |
| `#create_work_tree` | Atomic: create a worktree of any repo under `repos/` for the active session |
| `#define_deployment` | Author a production deployment definition (risk / pre-flight / steps / validation / rollback) |
| `#start_guided_deployment` | Execute a deployment definition step-by-step, capturing evidence, with rollback on failure |
| `#set-repo-doctrine` | Deduce and persist repo context (purpose, stack, folder conventions) |
| `#configure-integrations` | Set up Jira and GitHub integration schemas |
| `#pause_work_session` | Save current state; worktrees and branches remain intact |
| `#resume_work_session` | Reactivate a paused or stopped session; refreshes the agentic-sdlc tools worktree |
| `#stop_work_session` | Hard stop — commit, remove target-repo worktrees, retain branches |
| `#end_work_session` | Close a completed session — remove all worktrees, mark done |
| `#sync-work` | Stage, commit, and push current work in a session worktree |
| `#open-pr` | Open a new PR or refresh an existing PR description |
| `#review-pr` | Triage and address review comments or give structured feedback |
| `#find-session` | Search and list sessions by description or status |
| `#create-adr` | Guided creation of an Architecture Decision Record |
| `#enable_flex_mode` | Unlock autonomous write operations for a declared sandbox environment |
| `#override-tool-priority` | Temporarily force CLI/API usage over MCP for named tools |

### SDLC management (project-manager)

The `project-manager` **agent** (`.agents/agents/`) owns the flow of work in
the sibling `work-sessions` repo — intake, triage, grooming,
backlog/WIP health, bottleneck/blocker detection, planning, and retros. It
manages the flow, not the implementation. Ask it broad questions ("how's the
board?", "are we overloaded?") or invoke the atomic ceremonies directly:

| Command / Skill | Purpose |
|---|---|
| `#triage-inbox` | Turn raw `work/INBOX.md` captures into shaped `backlog.json` items (priority + weight) |
| `#groom-item` | Assess one item for readiness (why/what, acceptance criteria, test scenarios, missing info); flip `grooming → ready` |
| `#review-backlog` | Backlog health — stale/outstanding items, Jira status mismatches; regenerate `work/WORK_STATE.md` |
| `#review-wip` | WIP health — load & importance, on-hold-too-long, blockers, bottlenecks; whether to finish / get help / drop |
| `#plan-cycle` | Planning ceremony — prioritize, break down large items, set a roadmap → `planning/` |
| `#run-retro` | Retrospective — what went well/wrong, when to have asked for help, action items → `retros/` |
| `planning` *(skill)* | Natural-language entry to the planning ceremony — refreshes health first, then runs `#plan-cycle` |
| `design` *(skill)* | Design-first — define interface/contract/schema as a SPEC before implementation |

## Extending this framework

This repo ships with a general-purpose command/skill set and two integration
templates (Jira/Atlassian, AWS). To adapt it to your org:

- Fill in `.agents/rules/atlassian.instructions.md` and `aws.instructions.md`
  with your real projects, fields, and conventions.
- Add new `.agents/rules/*.instructions.md` files for other systems you
  integrate with (a different cloud provider, a monorepo build tool, a
  different ticketing system) — list them in `AGENTS.md` → Integration Schemas.
- Add new `.agents/skills/<name>/SKILL.md` for org-specific SOPs (a
  multi-step operational procedure you want an agent to run consistently).
- Add new `.agents/commands/<name>.prompt.md` for atomic, reusable operations.

## Contributing

Use the commands/skills above to manage work sessions, open PRs, and author ADRs through the agent. Global agent behaviour and tool-priority rules are defined in [`AGENTS.md`](AGENTS.md) (symlinked as `CLAUDE.md` and `.github/copilot-instructions.md`).
