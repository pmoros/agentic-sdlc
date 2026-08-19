# scripts/

Deterministic automation the `.agents/commands` shell out to, so the prompts
stay small and the mechanical parts are testable rather than re-derived by the
agent each time.

| Path | Purpose | Backs |
|---|---|---|
| `create-worktree.sh` | Create/refresh/promote a git worktree of any repo under `repos/` (read-only-source policy, CoW node_modules) | `#create_work_tree`, `init-session.sh` |
| `init-session.sh` | Scaffold a session folder in `work-sessions`, register it in `SESSIONS_STATE.md` **and the portfolio `work/wip.json` tracker** (via `lib/upsert_wip.py`), create the agentic-sdlc tools worktree, wire up tmux | `#initialize_work_session_folder` |
| `lib/upsert_wip.py` | Pure wip-upsert logic — idempotently register a session id as an `in progress` item in `work/wip.json`, moving it from `work/backlog.json` if groomed there (per `work/template.json` shape) | `init-session.sh` |
| `define-work-item.sh` | The canonical Work Item constructor — creates/reshapes `work/items/<id>.json` (one file per item, per-item `mkdir`-lock with PID-liveness stale-break) via `lib/define_work_item.py` | `#triage-inbox`, `#groom-item`, `init-session.sh` upsert path (ADH-008 item/episode split, in progress) |
| `lib/define_work_item.py` | Pure item-shaping logic — the single writing mechanism for a Work Item's fields; only explicitly-passed fields change, `sessions[]`/`history`/`current_state` are preserved on reshape | `define-work-item.sh` |
| `migrate-items-v2.sh` | One-time migration from `work/backlog.json`/`wip.json` (old shared-file store) to `work/items/<id>.json` (one file per item) — `--dry-run` (default)/`--commit` (staged + byte-identical-verified + all-or-nothing)/`--commit-cleanup`/`--verify`, via `lib/migrate_items.py` | ADH-008 item/episode split, one-time |
| `lib/migrate_items.py` | Pure migration logic — merges `backlog.json`/`wip.json`, parses `SESSIONS_STATE.md`'s registry table, shapes each migrated item (source fields untouched + new `id`/`sessions[]`), diffs for `--dry-run`, verifies for `--commit`/`--verify` | `migrate-items-v2.sh` |
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
| `tests/test_init_session.py` | `init-session.sh` folder+CONTEXT+registry+worktree+tmux **+ `work/wip.json` seeding / backlog→wip move / idempotency**, against a minimal work-sessions repo + scratch agentic repo |
| `tests/test_upsert_wip.py` | `lib/upsert_wip.py` pure logic — fresh-seed, backlog→wip move, blocked state, idempotency, no-clobber (plain dicts, no I/O) |
| `tests/test_session_log.py` | `session-log.sh` timestamped append to WORKLOG / CONTEXT, `--to` targeting, append-not-clobber, error paths |
| `tests/test_aws_login.py` | `aws-login.sh` expired/valid-token paths, `--all`/`--list`, allow-list enforcement — against a stubbed `aws` CLI, no real AWS |
| `tests/test_security_check.py` | `security-check.sh` secrets/shell/actions checks each catch a real planted issue and pass on clean fixtures — against throwaway repos, no touching this repo's own history |
| `tests/test_define_work_item.py` | `lib/define_work_item.py` pure logic — fresh-item seeding, field validation (status/scope enums), reshape preserves `sessions`/`history`/`current_state`, ticket-map merge (plain dicts, no I/O) |
| `tests/test_define_work_item_sh.py` | `define-work-item.sh` end-to-end — CLI validation, lock release on success, stale-lock-with-dead-PID is broken (not waited out), a live holder is never preempted (wrapper times out cleanly instead), same-item concurrent writers never corrupt the file, different-item writers never contend |
| `tests/test_migrate_items.py` | `lib/migrate_items.py` pure logic — backlog/wip merge + id-collision detection, `SESSIONS_STATE.md` table parsing, single first-episode `sessions[]` derivation, field preservation (including undocumented drifted fields), diff/verify field-set logic (plain dicts, no I/O) |
| `tests/test_migrate_items_sh.py` | `migrate-items-v2.sh` end-to-end — `--dry-run` writes nothing and is repeat-safe, `--commit`'s staging/verify/atomic-move sequence and refusal when `work/items/` already holds real content, stale-`.staging/`-from-an-interrupted-attempt is cleared and retried cleanly, one item failing verification aborts the whole commit with no partial `work/items/` visible, standalone `--verify`, `--commit-cleanup` renames to `*.pre-migration.bak` and never deletes/overwrites |

`scripts/tests/_harness.py` holds the shared helpers (throwaway git repos, a
minimal work-sessions repo, a temp-dir base `TestCase`). Tests never touch real
AWS, real remotes, the real work-sessions repo, or the user's real tmux sessions.

When adding a script (or a scriptable command): put the pure logic in a Python
module and test it directly; keep only AWS/SSM/git/tmux orchestration in a thin
`.sh` and test it end-to-end against fixtures; then reduce the prompt to
invoking the script + the genuinely-judgmental interpretation.
