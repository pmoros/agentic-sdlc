# scripts/

Deterministic automation the `.agents/commands` shell out to, so the prompts
stay small and the mechanical parts are testable rather than re-derived by the
agent each time.

| Path | Purpose | Backs |
|---|---|---|
| `create-worktree.sh` | Create/refresh/promote a git worktree of any repo under `repos/` (read-only-source policy, CoW node_modules) | `#create_work_tree`, `init-session.sh` |
| `init-session.sh` | Scaffold a session folder in `work-sessions`, register it in `SESSIONS_STATE.md` **and the per-item store `work/items/<id>.json`** (via `define-work-item.sh`), create the agentic-sdlc tools worktree, wire up tmux. `--reopen-item <item-id>` (ADH-011) starts a new episode of an existing item instead — computes `<item-id>--eN` and calls `--open-episode`, never seeds a fresh item. Refuses up front (before any side effect) if `work/items/` isn't populated yet but `backlog.json`/`wip.json` still hold real content — run `migrate-items-v2.sh` first | `#initialize_work_session_folder` |
| `define-work-item.sh` | The canonical Work Item constructor — creates/reshapes `work/items/<id>.json` (one file per item, per-item `mkdir`-lock with PID-liveness stale-break), regenerates the derived views, and (via `--record-event`/`--current-state`/`--open-episode`/`--close-episode`) is how the session lifecycle records its own events through the same locked write path — via `lib/define_work_item.py`. `--parent`/`--promote` (ADH-012) link/unlink a Work Item hierarchy; both first acquire a second, shared `work/items/.parent-link.lock/` (generalized from the per-item lock mechanism) before validating and acquiring the item's own lock — closes a real cross-item race that an unguarded validation read would otherwise allow. `--roadmap-step`/`--roadmap-owner`/`--roadmap-target-date`/`--roadmap-type` (ADH-014) append one entry to `roadmap[]` — the last remaining constructor gap, append-only like `history`. ADH-014 also adds two guardrails enforced here for every caller, not just `#define-work-item`: `--status done` + `--close-episode` together is refused at parse time; a plain `--status done` while `sessions[]`'s last entry is still open is refused **inside the item's own lock, immediately before the write** (not a pre-lock read — closes a real TOCTOU race Gate A traced by hand) | `#triage-inbox`, `#groom-item`, `init-session.sh`, `#end_work_session`, `#plan-cycle`, `#define-work-item` (ADH-008 item/episode split, ADH-011 episode identity, ADH-012 hierarchy, ADH-014 roadmap + guardrails — supersedes the old `lib/upsert_wip.py`, which duplicated this shaping logic separately and had already diverged from it) |
| `lib/define_work_item.py` | Pure item-shaping logic — the single writing mechanism for a Work Item's fields; only explicitly-passed fields change, `sessions[]`/`history`/`current_state` are preserved on reshape **unless the caller opts in via `record_event`/`current_state_description`/`open_episode`/`close_episode`** (the session-lifecycle escape hatch — `init-session.sh`/`#end_work_session` use it, ordinary shaping calls don't). `open_episode`/`close_episode` (ADH-011) append/close a `sessions[]` entry (`episode_id`/`episode_number`/`folder`/`opened`/`closed`/`outcome`); `close_episode(..., outcome="done")` is the only path that ever sets an item's top-level `status` to `done`. `parent_id`/`promote` (ADH-012) are plain reshape-tier fields, not session-lifecycle-gated — `define_item()` itself only sets/clears the field; the module's one deliberate exception to "only `main` does I/O", `validate_parent_link`/`validate_promote`, does the actual cross-item hierarchy checks (self-parent, nonexistent target, already-nested, already-a-parent). `roadmap_step` (ADH-014) appends one `{step, owner, target_date, type}` dict to `item["roadmap"]`, requiring non-empty `step`/`owner` — the `--status done`/open-episode guardrail deliberately does **not** live here, since it needs to read `sessions[]` to decide whether `status` may be set at all, a caller-level decision handled in `define-work-item.sh` itself | `define-work-item.sh` |
| `migrate-items-v2.sh` | One-time migration from `work/backlog.json`/`wip.json` (old shared-file store) to `work/items/<id>.json` (one file per item) — `--dry-run` (default)/`--commit` (staged + byte-identical-verified, installed via a single atomic directory move)/`--commit-cleanup`/`--verify`, via `lib/migrate_items.py` | ADH-008 item/episode split, one-time |
| `lib/migrate_items.py` | Pure migration logic — merges `backlog.json`/`wip.json`, parses `SESSIONS_STATE.md`'s registry table, shapes each migrated item (source fields untouched + new `id`/`sessions[]`), diffs for `--dry-run`, verifies for `--commit`/`--verify` | `migrate-items-v2.sh` |
| `migrate-sessions-state-episode-column.sh` | One-time, additive, idempotent migration: adds an `Item` column to `SESSIONS_STATE.md`'s registry table (`= Session ID` for every pre-ADH-011 row) — `--dry-run` (default)/`--commit` (timestamped `.bak` + atomic write)/`--verify`, via `lib/migrate_sessions_state.py` | ADH-011 episode identity, one-time |
| `lib/migrate_sessions_state.py` | Pure text transformation — inserts the `Item` column into the header/separator/every row of the markdown table, idempotent, non-table content untouched | `migrate-sessions-state-episode-column.sh` |
| `check-spec-complete.sh` | Confirms a session's `SPEC.md` has a non-empty `## Impact analysis` (Stakeholders/Components/Data dependencies/Side effects) before Gate A — via `lib/check_spec_complete.py` | design skill Gate A precondition (ADH-008) |
| `lib/check_spec_complete.py` | Pure logic — greps a SPEC's Impact Analysis subsection and reports which of the four required fields are missing/empty | `check-spec-complete.sh` |
| `session-tmux.sh` | Guarded tmux lifecycle helper (`ensure` / `attach-hint` / `kill`); loads the session `.env` into the tmux env on `ensure` | init/resume/stop/end |
| `aws-login.sh` | (Re)authenticate AWS SSO profiles — checks `sts get-caller-identity`, only runs `aws sso login` when expired, enforces the session `.env` allow-list | `#aws-reauth` |
| `session-log.sh` | Append a consistent timestamped line to a session's `WORKLOG.md` / `CONTEXT.md` activity log | session-state rule + lifecycle commands |
| `security-check.sh` | Secret scan (`gitleaks`) + shell static analysis (`shellcheck`) + workflow lint (`actionlint`) — same checks CI runs | `.github/workflows/ci.yml`, run manually before pushing |

Add org-specific scripts here as you need them — see the Tests section below
for the standard every new script should meet.

## Tooling versions

The tools `security-check.sh` shells out to (`gitleaks`, `shellcheck`,
`actionlint`) are pinned in `../.mise.toml` — run `mise install` once (after
`mise trust` on first use) to fetch exactly those versions. CI installs the
same pinned versions via the `jdx/mise-action` GitHub Action, so a clean local
run of `scripts/security-check.sh` should never disagree with CI.

## Tests

Every non-trivial script here ships with tests — this is a rule, not a
courtesy (see `.agents/rules/engineering.instructions.md` → Script Testing
Standard). Tests are Python `unittest.TestCase`, so they run with **either**
pytest or the stdlib runner, and the whole suite runs from one command:

```bash
# whole suite (pytest is installed into the local .venv):
.venv/bin/python -m pytest scripts -q

# dependency-free, stdlib only — per test directory (discover doesn't recurse
# into non-package subdirs, so point it at each one):
.venv/bin/python -m unittest discover -s scripts/tests -p 'test_*.py'
```

| Tests | What they cover |
|---|---|
| `tests/test_session_tmux.py` | `session-tmux.sh` name + ensure/exists/attach-hint/kill lifecycle (real tmux, collision-proof id, always torn down; skipped if tmux absent) |
| `tests/test_create_worktree.py` | `create-worktree.sh` detach/branch/refresh, dirty-source guard, arg validation — against throwaway bare+clone repos, no AWS/node |
| `tests/test_init_session.py` | `init-session.sh` folder+CONTEXT+registry+worktree+tmux **+ `work/items/<id>.json` seeding / reshaping a pre-groomed item / not touching other items**, plus the migration safety guard (refuses when `work/items/` is unpopulated but `backlog.json`/`wip.json` hold real content, before any side effect), **plus `--reopen-item` (ADH-011): refuses on a nonexistent item, computes `<item-id>--eN` and calls `--open-episode`, never creates a second item file, `SESSIONS_STATE.md`'s new `Item` column on both reopen and ordinary rows, episode numbering past 2** — against a minimal work-sessions repo + scratch agentic repo |
| `tests/test_session_log.py` | `session-log.sh` timestamped append to WORKLOG / CONTEXT, `--to` targeting, append-not-clobber, error paths |
| `tests/test_aws_login.py` | `aws-login.sh` expired/valid-token paths, `--all`/`--list`, allow-list enforcement — against a stubbed `aws` CLI, no real AWS |
| `tests/test_security_check.py` | `security-check.sh` secrets/shell/actions checks each catch a real planted issue and pass on clean fixtures — against throwaway repos, no touching this repo's own history |
| `tests/test_define_work_item.py` | `lib/define_work_item.py` pure logic — fresh-item seeding, field validation (status/scope enums), reshape preserves `sessions`/`history`/`current_state`, ticket-map merge, the `record_event`/`current_state_*`/`last_synced`/`open_episode`/`close_episode`/`parent_id`/`promote`/`roadmap_step` opt-in overrides — **episode lifecycle (ADH-011): open/close against an already-populated `sessions[]`, refuses opening while the last episode is still open, numbering past episode 2, the structurally-empty backfill branch, `outcome: done` sets top-level `status`**; **hierarchy (ADH-012): `parent_id` sets, `promote` clears, both together raises**; **roadmap (ADH-014): appends to an empty/existing `roadmap[]` without touching prior entries, no-op when omitted, requires non-empty `step`/`owner`** (plain dicts, no I/O) |
| `tests/test_validate_parent_link.py` | `lib/define_work_item.py`'s `validate_parent_link`/`validate_promote` (ADH-012) — the one deliberate I/O-touching exception in that module, kept in its own file so `test_define_work_item.py`'s "plain dicts, no I/O" description stays accurate. Self-parent, nonexistent target, target already has a parent, item is already a parent to something else, re-parenting to a different parent is allowed, linking a not-yet-created item is allowed, promote with/without an existing parent — against a real tmp directory |
| `tests/test_define_work_item_sh.py` | `define-work-item.sh` end-to-end — CLI validation, `--record-event`/`--current-state`/`--last-synced`/`--open-episode`/`--close-episode` (requires `--outcome`)/`--parent`/`--promote` (mutually exclusive) flags, lock release on success, stale-lock-with-dead-PID is broken (not waited out), a live holder is never preempted (wrapper times out cleanly instead), same-item concurrent writers never corrupt the file, different-item writers never contend, views regenerate after every write — **hierarchy (ADH-012): link/refuse-self-parent/refuse-nonexistent-target/refuse-two-level-chain, promote clears+preserves history, re-parenting is allowed, and a genuine concurrency regression test that launches two racing `--parent` calls on different items as real subprocesses and asserts the multi-level-chain race Gate A traced never actually forms**; **roadmap + guardrails (ADH-014): `--roadmap-step` appends with `TBD`/`standard` defaults, `--roadmap-owner`/`--roadmap-target-date`/`--roadmap-type` all refused without `--roadmap-step`, `--roadmap-step` without `--roadmap-owner` refused, combines cleanly with `--parent`; `--status done` + `--close-episode` together refused; `--status done` refused when the last episode is still open and allowed when it isn't or none ever existed; `--roadmap-step` also combines cleanly with `--open-episode`; a real-subprocess concurrency test for the status-done/open-episode race, closing episode 1 first so `--open-episode` can actually succeed and the race is reachable (Gate B: the original precondition raced against a brand-new item, whose synthesized episode 1 is always open, so `--open-episode` always refused regardless of timing — the race was structurally unreachable, not merely hard to hit; corrected version reliably catches the pre-fix ordering, confirmed via mutation testing both ways — see WORKLOG)** |
| `tests/test_migrate_items.py` | `lib/migrate_items.py` pure logic — backlog/wip merge + id-collision detection, `SESSIONS_STATE.md` table parsing, single first-episode `sessions[]` derivation, field preservation (including undocumented drifted fields), diff/verify field-set logic (plain dicts, no I/O) |
| `tests/test_migrate_items_sh.py` | `migrate-items-v2.sh` end-to-end — `--dry-run` writes nothing and is repeat-safe, `--commit`'s staging/verify/single-atomic-move sequence and refusal when `work/items/` already holds real content, stale-staging-from-an-interrupted-attempt is cleared and retried cleanly, one item failing verification (or the final atomic move itself failing) aborts the whole commit with no partial `work/items/` visible, standalone `--verify`, `--commit-cleanup` renames to `*.pre-migration.bak` and never deletes/overwrites |
| `tests/test_migrate_sessions_state.py` | `lib/migrate_sessions_state.py` pure logic — header/separator/row transformation, `_none yet_` placeholder gets an empty (not literal) Item cell, idempotent on a second call, non-table prose untouched, no-table-found is a no-op (plain text, no I/O) |
| `tests/test_migrate_sessions_state_sh.py` | `migrate-sessions-state-episode-column.sh` end-to-end — `--dry-run` writes nothing, `--commit` adds the column + writes a timestamped `.bak` + preserves the trailing newline + is idempotent, `--verify` fails before/passes after commit and catches a real mismatch, a prose line merely containing `\|` is never parsed as a table row |
| `tests/test_check_spec_complete.py` | `lib/check_spec_complete.py` pure logic — missing-field detection for each of the four Impact Analysis bullets (plain text, no I/O) |
| `tests/test_check_spec_complete_sh.py` | `check-spec-complete.sh` end-to-end — CLI validation, non-zero exit + missing-field listing on an incomplete SPEC, zero exit on a complete one |

`scripts/tests/_harness.py` holds the shared helpers (throwaway git repos, a
minimal work-sessions repo, a temp-dir base `TestCase`). Tests never touch real
AWS, real remotes, the real work-sessions repo, or the user's real tmux sessions.

When adding a script (or a scriptable command): put the pure logic in a Python
module and test it directly; keep only AWS/SSM/git/tmux orchestration in a thin
`.sh` and test it end-to-end against fixtures; then reduce the prompt to
invoking the script + the genuinely-judgmental interpretation.
