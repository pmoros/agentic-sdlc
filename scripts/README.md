# scripts/

Deterministic automation the `.agents/commands` shell out to, so the prompts
stay small and the mechanical parts are testable rather than re-derived by the
agent each time.

| Path | Purpose | Backs |
|---|---|---|
| `create-worktree.sh` | Create/refresh/promote a git worktree of any repo under `repos/` (read-only-source policy, CoW node_modules) | `#create_work_tree`, `init-session.sh` |
| `init-session.sh` | Scaffold a session folder in `work-sessions`, register it, create the agentic-sdlc tools worktree, wire up tmux | `#initialize_work_session_folder` |
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
| `tests/test_init_session.py` | `init-session.sh` folder+CONTEXT+registry+worktree+tmux, against a minimal work-sessions repo + scratch agentic repo |
| `tests/test_session_log.py` | `session-log.sh` timestamped append to WORKLOG / CONTEXT, `--to` targeting, append-not-clobber, error paths |
| `tests/test_aws_login.py` | `aws-login.sh` expired/valid-token paths, `--all`/`--list`, allow-list enforcement — against a stubbed `aws` CLI, no real AWS |
| `tests/test_security_check.py` | `security-check.sh` secrets/shell/actions checks each catch a real planted issue and pass on clean fixtures — against throwaway repos, no touching this repo's own history |

`scripts/tests/_harness.py` holds the shared helpers (throwaway git repos, a
minimal work-sessions repo, a temp-dir base `TestCase`). Tests never touch real
AWS, real remotes, the real work-sessions repo, or the user's real tmux sessions.

When adding a script (or a scriptable command): put the pure logic in a Python
module and test it directly; keep only AWS/SSM/git/tmux orchestration in a thin
`.sh` and test it end-to-end against fixtures; then reduce the prompt to
invoking the script + the genuinely-judgmental interpretation.
