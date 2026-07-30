# LiteLLM gateway — the $200/month hard cap (runbook)

This is the **minimal gateway that makes the $200/month ceiling real and un-bypassable**
(layers 1–3 of the budget design in `../../docs/phase-2-worker-and-budget.md`). Stand this
up **before** the first money-spending autonomous run.

## What it does

- Enforces a **global $200/month cap** (`litellm_settings.max_budget: 200`, `budget_duration: "1mo"`). When hit, the gateway refuses all traffic.
- Persists spend in **Postgres**, so a restart does **not** reset the month's counter (no surprises).
- Issues **worker virtual keys** with their own smaller budgets. Workers use a virtual key + `ANTHROPIC_BASE_URL=http://localhost:4000`; the real `ANTHROPIC_API_KEY` lives **only inside the gateway**, so a worker cannot bill around the cap.

## Prereqs

- Docker (Docker Desktop or OrbStack) running on macOS.
- Your Anthropic API key (per-token billing account — not a Pro subscription).

## Launch

```sh
cd scripts/gateway
cp .env.example .env          # then edit .env: set ANTHROPIC_API_KEY, LITELLM_MASTER_KEY, POSTGRES_PASSWORD
docker compose up -d          # starts postgres + litellm on :4000
curl -s http://localhost:4000/health/liveliness   # expect "I'm alive!" or 200
```

## Mint a worker key (scoped + budgeted)

```sh
set -a; . ./.env; set +a        # export LITELLM_MASTER_KEY for the script
./gen-key.sh                    # $30/month worker key on the coder+classifier lanes
# WORKER_MONTHLY_BUDGET=50 ./gen-key.sh   # to change the per-worker budget
```

Point the worker at the gateway with the returned key as its API key + `ANTHROPIC_BASE_URL=http://localhost:4000`.

## Watch spend (the "no surprises" checks)

```sh
# global spend to date this period
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://localhost:4000/global/spend
# per-key spend / budgets
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://localhost:4000/global/spend/keys
```

When the global cap is reached, requests return a budget-exceeded error (HTTP 400) instead of spending. The local guard (`../budget.py`) is the *earlier* graceful stop at 90% — this gateway cap is the final wall.

## Change / raise the cap

Edit `max_budget` in `litellm-config.yaml`, then `docker compose restart litellm`. Keep the sum of worker-key budgets under the global cap.

## Security

- **Never commit `.env`** — it holds the real key (gitignored). `.env.example` uses placeholders only.
- Workers must receive a **virtual key**, never `ANTHROPIC_API_KEY`.
- AWS creds are only needed to enable the non-Anthropic Bedrock lanes later.

## Verify before relying on it (honesty notes)

- **Pin the LiteLLM image** to a specific version tag (the compose uses `main-stable`).
- Confirm the current LiteLLM field/endpoint names against the LiteLLM docs (they evolve): `max_budget`/`budget_duration`, `/key/generate`, `/global/spend`. The cap concept is stable; exact endpoints may shift by version.
- Do a **cheap end-to-end test** first: mint a key with a tiny budget (e.g. `WORKER_MONTHLY_BUDGET=0.10`), make one small request through it, and confirm it blocks once the tiny budget is exceeded — proving the enforcement path works before trusting the $200 cap.
