# autonomous-workflows

A headless, autonomous **multi-agent coding fleet** built on Claude Code. You hand it a
task; it decomposes the work, launches N workers (each a `claude -p` run in its own git
branch), keeps every worker inside a **guardrail + cost/rate-limit budget**, joins the
branches back with conflict + safety checks, and reports a **tested evaluation-metrics
harness** so success is measured, not asserted.

The design is deliberately **pure decision cores** (no I/O — fully unit-tested) wrapped by
**thin I/O shells** (`run-worker.sh`, the gateway). That split is why the whole control
logic is testable offline.

## Two lanes (the `LANE` switch)

A *lane* is the auth + billing path a worker runs on:

| | `subscription` (default) | `api` (opt-in) |
|---|---|---|
| **Auth** | Max-plan OAuth via Keychain; **no API creds in env** | LiteLLM virtual key (worker never sees the raw key) |
| **Constraint** | rate-limit **windows** (5h + two weekly caps) | **dollars** ($200/mo hard cap) |
| **Guard** | `window_guard.py` | `budget.py` |
| **On exhaustion** | **pause-until-reset**, never fail; no auto-spend | halt below the reserve |
| **Cost basis** | `estimated` (list-price proxy) | `billed` (real) |
| **Gateway?** | no | yes (`gateway/`, `docker compose up`) |

On the subscription lane, `run-worker.sh` scrubs the **complete documented
auth-precedence chain** and aborts if `apiKeyHelper` is configured — so a stray key in
your shell can never silently flip a worker back to paid billing.

## Module map

| File | Role |
|---|---|
| `decomposition.py` | split one task into subtasks (validates deps / overlap) |
| `routing.py` | pick the model tier per task (planner→Opus, coder→Sonnet, classifier→Haiku) |
| `policy.py` | authorization classifier — action **ALLOWED** unattended vs **GATED** (needs a human) |
| `budget.py` | api-lane dollar guard (pre-flight, below the gateway's hard cap) |
| `window_guard.py` | subscription-lane rate-limit-window guard (burn ledger + limit-error parse) |
| `orchestrator.py` | plan runs, admission-control the fleet, decide the N-branch join, stage machine |
| `supervisor.py` | per-turn decision: continue / gate / execute / halt / pause |
| `fanout.py` | dep-aware bounded-concurrency scheduler + run manifest + teardown plan |
| `integrate.py` | real N-branch merge onto an integration branch + merged-tree QA |
| `metrics.py` | aggregate run-records → cost/quality/safety numbers + phase go/no-go gates |
| `run-worker.sh` | the launcher: lane seam, env scrub, full `stream-json` trace capture |
| `gateway/` | LiteLLM $200/mo hard-cap config (api lane only) — see `gateway/README.md` |

## Quickstart

```sh
# subscription lane (default) — no gateway, no dollars
autonomous-workflows/run-worker.sh t1 "Read src/foo.py and add a docstring, then stop"

# pick a tier + constrain tools; prompt from a file with @path
LANE=subscription ROLE=coder WORKER_TOOLS="Read,Edit" \
  autonomous-workflows/run-worker.sh t1 @task.md

# api lane — start the gateway first (see gateway/README.md)
LANE=api BUDGET=5 autonomous-workflows/run-worker.sh t1 "…"
```

Env knobs: `LANE` (subscription|api), `ROLE` (planner|coder|classifier or a task type),
`MODEL` (explicit override), `WORKER_TOOLS`, `BUDGET` (api per-key $/mo cap), `GATEWAY`,
`RUN_RECORDS_DIR` (output dir).

## Run flow

```
decompose → plan_runs → admit → schedule/launch → supervise → join → teardown → metrics
```

Admission uses `orchestrator.fanout_windows_ok` (subscription) or `fanout_budget_ok`
(api); the join uses `join_input` (guarded pause recognition) + `join_decision`
(precedence `halt_violation > partial_review > waiting_rate_limit > needs_human_merge >
ready_for_final_review`); metrics via `metrics.aggregate` + `evaluate_gates(phase)`.

## Tests

```sh
cd autonomous-workflows && python3 -m pytest          # 216 tests, all offline
```

## Provenance

Built test-first across the `ADH-001` (base fleet) and `ADH-003` (subscription-lane
pivot) work sessions and promoted here. The subscription lane is intended for **personal
single-user automation** (currently permitted, not the recommended path for shared
production automation).
