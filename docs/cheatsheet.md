# Command Cheatsheet

Quick reference for every command and script flag in the toolbox. See
[`architecture.md`](architecture.md) for how it all fits together.

## Session lifecycle

| Command | What it does |
|---|---|
| `start-work-session` (skill) | Gather ticket/goal/scope, scaffold the session folder + worktree(s). Offers to **reopen** if the target id already has a `done`/`on-hold`/`in-review` item |
| `#initialize_work_session_folder` | Atomic: create the session folder, register it, set up the mandatory `worktrees/agentic-sdlc` tools worktree |
| `#create_work_tree` | Atomic: add one more target-repo worktree to the active session |
| `#pause_work_session` | Save state, return to main — without closing |
| `#resume_work_session` | Reactivate a paused/stopped session in a **new** conversation |
| `#stop_work_session` | Hard stop — commit, remove target-repo worktrees, keep branches |
| `#end_work_session` | Close a completed session — closes the item (`--close-episode --outcome done`), removes all worktrees, batched Jira/Confluence checkpoint |
| `#sync-work` | Commit + push the current session's worktree, any time |
| `#open-pr` | Open/refresh a PR |
| `#review-pr` | Address PR comments (author) or give structured feedback (reviewer) |
| `#find-session` | Search sessions by description or status |
| `#create-adr` | Guided ADR creation |

## Portfolio / backlog

| Command | What it does |
|---|---|
| `#triage-inbox` | Shape raw `INBOX.md` lines into Work Items (priority + scope) |
| `#groom-item [id]` | Readiness checklist (why/what/AC/test-scenarios); flip `grooming → ready`. Shows parent/children roll-up; can link a breakdown right there via `--parent` |
| `#review-backlog` | Stale/aging items, Jira mismatches, roadmap gaps, hierarchy roll-up; regenerates `WORK_STATE.md` |
| `#review-wip` | WIP load, on-hold-too-long, blockers, bottlenecks; keep-going / ask-for-help / drop call |
| `#plan-cycle` | Prioritize, break down `L`/`XL` items (now actually links via `--parent`), roadmap doc → `planning/` |
| `#run-retro` | What went well/wrong, when to have asked for help → `retros/` |

## `define-work-item.sh` — the one constructor

```bash
scripts/define-work-item.sh <id> [flags...] --work-sessions-repo <path>
```

Only explicitly-passed fields change. Nothing is ever hand-edited in
`work/items/<id>.json` — always through this script.

| Flag | Effect |
|---|---|
| `--title <t>` | Item title (new item: seeded from `--description`/`--task-type` if omitted) |
| `--description <d>` | Item description |
| `--status <s>` | `grooming\|ready\|in progress\|on hold\|in review\|done` |
| `--priority <p>` | Jira priority scale value |
| `--scope <XS\|S\|M\|L\|XL>` | Effort estimate |
| `--ticket <id-or-url>` | Merged into `tickets.main-bug-tracking` |
| `--task-type <type>` | `feat\|fix\|chore\|refactor\|docs\|spike` — seeds a new item's title only |
| `--record-event <action> [--by <name>]` | **Opt-in.** Append one `history` entry |
| `--current-state <desc> [--blocked]` | **Opt-in.** Overwrite `current_state` |
| `--last-synced <ISO8601>` | **Opt-in.** Set the close-checkpoint watermark |
| `--open-episode <session-id>` | **Opt-in.** Reopen as a new episode — appends `sessions[]`, `status → in progress` |
| `--close-episode <session-id> --outcome <done\|stopped\|paused>` | **Opt-in.** Close an episode; `outcome: done` also sets item `status → done` |
| `--parent <parent-item-id>` | Link as a sub-item (validated: no self-parent, no two-level chain, target must not already be nested or already-a-parent) |
| `--promote` | Clear `parent_id` (de-aggregate). Refuses if there's nothing to clear |

## `init-session.sh` — session scaffolding

```bash
scripts/init-session.sh <session-id> --goal "<goal>" [flags...]
scripts/init-session.sh --reopen-item <item-id> --goal "<goal>" [flags...]   # no positional id
```

| Flag | Effect |
|---|---|
| `--goal <text>` | Required. Recorded in `CONTEXT.md` |
| `--ticket <id-or-url>` | Recorded in the Tickets table |
| `--scope <XS\|S\|M\|L\|XL>` | Recorded in the Overview line |
| `--task-type <type>` | `feat\|fix\|chore\|refactor\|docs\|spike` |
| `--blockers <text>` | Sets `Blocked: yes` instead of the goal line |
| `--reopen-item <item-id>` | Start episode N+1 of an existing item — the session id (`<item-id>--eN`) is computed for you, item must already exist |

## Migration tools (one-time, dry-run/commit/verify)

| Script | Purpose |
|---|---|
| `migrate-items-v2.sh` | `backlog.json`/`wip.json` → `work/items/<id>.json`. `--dry-run` / `--commit` (staged + byte-verified, atomic install) / `--commit-cleanup` / `--verify` |
| `migrate-sessions-state-episode-column.sh` | Add `SESSIONS_STATE.md`'s `Item` column. `--dry-run` / `--commit` (backed up + atomic write) / `--verify` |

## Common recipes

**Reopen a done item as a new episode:**
```bash
scripts/init-session.sh --reopen-item ADH-020 --goal "Pick this back up"
```

**Close a session (the item reaches `done`):**
```bash
scripts/define-work-item.sh ADH-020 --close-episode ADH-020 --outcome done \
  --work-sessions-repo <path>
# (--close-episode <session-id> — use the literal session id, --eN suffix if it's episode >= 2)
```

**Link a sub-item to a parent (epic breakdown):**
```bash
scripts/define-work-item.sh ADH-021 --description "..." --status grooming \
  --parent ADH-020 --work-sessions-repo <path>
```

**De-aggregate a sub-item back to independent:**
```bash
scripts/define-work-item.sh ADH-021 --promote --work-sessions-repo <path>
```

**Record a lifecycle event without changing any field:**
```bash
scripts/define-work-item.sh ADH-020 --record-event "waiting on review" \
  --by "#review-wip" --work-sessions-repo <path>
```

**Check what a candidate reopen id already looks like, before starting:**
```bash
python3 -c "import json; d=json.load(open('work/items/ADH-020.json')); \
print(d['status'], d.get('sessions'))"
```
