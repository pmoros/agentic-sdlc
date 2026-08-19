---
agent: agent
description: Guided ad hoc control-plane maintenance for one Work Item — show current state, confirm the change, apply it via the canonical constructor. Two tiers of guardrail for lifecycle-adjacent flags.
---

# Define Work Item

Ad hoc maintenance for a single `work/items/<id>.json`, for the cases no
ceremony command covers — a stuck item, a one-off correction, recording a
`roadmap` step, closing sessions after the fact. It is a thin, guided
wrapper around the already-fully-built canonical constructor
`scripts/define-work-item.sh`; it adds no new write mechanics of its own.
`<work>` is the sibling `../work-sessions` repo.

This command never bypasses `scripts/define-work-item.sh`'s own hard
refusals (see § Tier 1 below) — those are enforced in the script itself,
for every caller, not just here.

## Step 1 — Identify the item

Take the item ID from the invocation (e.g. `define-work-item ADH-020`). If
none was given, ask for one — this command operates on exactly one item per
call (`scripts/define-work-item.sh`'s per-item lock already makes it
strictly single-item; there is no batch mode).

## Step 2 — Load and show current state

Read `<work>/work/items/<id>.json` directly — never `backlog.json`/
`wip.json`/`archive.json` (generated, read-only views; a `--status` change
here won't appear there until the next `regenerate-views.sh` run,
irrelevant for this command's own read).

Display **every** field, not the thin view-shape subset: `title`,
`description`, `status`, `priority`, `scope`, `tickets`, `task_type`,
`current_state`, `last_synced`, `history` (count + most recent 2–3
entries), `roadmap` (all entries), `sessions[]` (all entries, flagging
whether the last one is still open), `parent_id`. For hierarchy, mirror
`#groom-item`'s Step 2 display:
- If `parent_id` is set, read that parent and show its title + status in
  one line.
- Otherwise scan `<work>/work/items/*.json` for any item whose `parent_id`
  equals this one; list them (id/title/status) if any exist.

If the invocation had no flags (**bare** shape), stop here and ask what to
change. If it had flags (**flagged** shape), continue to Step 3 with the
state just loaded.

## Step 3 — Show current-vs-proposed

For exactly the fields the flags given would change, show a compact
current → proposed table. Fields not mentioned by any flag are unaffected —
say nothing about them here (they're already visible from Step 2).

**No-op check**: if every proposed value is identical to its current value,
say so explicitly — *"No changes: `--priority Major` already matches the
current value."* — and stop. Never silently "succeed" with an empty diff
unremarked.

## Step 4 — Guardrails

Two tiers, distinguished by whether the flag risks actual data corruption
or only skips a ceremony command's convenience. Only evaluate a tier's
table row if the corresponding flag is present in this call.

### Tier 1 — enforced by the script itself, not this command

`scripts/define-work-item.sh` itself hard-refuses, before any write:
- `--status done` (without `--close-episode`) when the item's `sessions[]`
  last entry has `closed: null` — refuses, pointing at `--close-episode
  --outcome done`.
- `--status done` combined with `--close-episode` in the same call —
  always refused, any outcome.

Nothing for this command to do here except **not preempt it** — if Step 3's
diff includes a plain `--status done` and Step 2's `sessions[]` display
already shows an open last entry, say so plainly before even attempting the
call ("this will be refused — the last episode is still open; use
`--close-episode <session-id> --outcome done` instead") rather than running
it and surfacing a raw script error as the first sign of trouble. This is a
UX courtesy, not the actual gate — the script's own check is authoritative
either way.

### Tier 2 — warn, don't block; requires genuine human confirmation

| Flag here | Ceremony command that also does this | What the ceremony adds that this command won't |
|---|---|---|
| `--status "in progress"` | `start-work-session` | Session folder, worktree(s), tmux, item-id ⇔ session-id linkage |
| `--close-episode --outcome done` (bypassing the close-checkpoint) | `#end_work_session` | Batched Jira/Confluence checkpoint, worktree removal, tmux teardown |
| `--open-episode` | `start-work-session`'s reopen-offer step | Computes the correct `--eN` session id, scaffolds the new episode's folder/worktree |

If any of these flags is present, show the matching warning — name the
ceremony command and exactly what it additionally does — then ask for
confirmation before proceeding. **This confirmation must be a genuine,
explicit human response** — per `AGENTS.md` § Approval Protocol ("wait for
explicit user approval... never infer approval from context — it must be
the most recent user message"). This command can in principle be invoked by
an autonomous/orchestrator caller; its Tier 2 confirmation is not exempt
from that rule just because it's phrased as a yes/no prompt rather than a
"guarded write" — do not treat any inferred, prior, or agent-generated
signal as satisfying it.

Every other flag (`title`, `description`, `priority`, `scope`, `ticket`,
`--parent`/`--promote`, `--roadmap-step` and its companions) needs neither
tier — plain control-plane reshaping, no ceremony attached, no corruption
risk.

## Step 5 — Re-check before applying

If any real time passed between Step 3's diff (or Step 4's confirmation)
and actually applying the change — e.g. the user paused mid-conversation —
re-read the item fresh immediately before the call, exactly like
`#end_work_session`'s "check live, immediately before firing" rule for
multi-hop Jira transitions. If the item changed underneath (another caller
wrote to it meanwhile), re-show the diff against the *current* state and
re-confirm rather than applying a decision made against stale data. For an
ordinary single-turn confirm-then-apply, this is a no-op — the item hasn't
had time to change — so don't manufacture a re-read where nothing could
plausibly have shifted.

## Step 6 — Apply

Call the constructor with exactly the flags implied by the confirmed
changes:

```bash
scripts/define-work-item.sh <id> \
  [--title <t>] [--description <d>] [--status <s>] \
  [--priority <p>] [--scope <XS|S|M|L|XL>] [--ticket <id-or-url>] \
  [--parent <parent-id> | --promote] \
  [--roadmap-step "<text>" --roadmap-owner "<name>" \
    [--roadmap-target-date <date>] [--roadmap-type <type>]] \
  [--open-episode <session-id> | --close-episode <session-id> --outcome <done|stopped|paused>] \
  --record-event "<what changed and why>" --by "#define-work-item" \
  --work-sessions-repo <work-sessions-repo>
```

Always pass `--record-event`/`--by` for a flagged call — an ad hoc
control-plane edit outside any ceremony command is exactly the kind of
change `history` exists to make traceable. Omit `--record-event` only for
a bare-invocation call that turned out to be a no-op (Step 3 already
stopped before reaching here).

`--roadmap-step` requires `--roadmap-owner`; if the user didn't supply an
owner, ask for one rather than defaulting or omitting it — the script
itself refuses the call without it.

If the script refuses (Tier 1, or a validation error), show its exact
message — it already names the correct alternative — and stop; do not
retry with different flags on the user's behalf.

## Step 7 — Report

On success, show the item's new state for exactly the fields that changed
(re-read the file rather than assuming the write matched the request). On
a Tier 1 refusal or validation error, show the message and suggest the
named alternative. Offer no further action beyond what was asked — this is
a one-off maintenance command, not the start of a new ceremony.
