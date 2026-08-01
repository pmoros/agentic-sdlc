#!/usr/bin/env bash
#
# Mint a WORKER virtual key with its own monthly budget, scoped to the coder +
# classifier lanes. The worker uses THIS key (with ANTHROPIC_BASE_URL=http://localhost:4000)
# — never the raw ANTHROPIC_API_KEY — so it physically cannot spend outside the gateway's
# accounting or exceed the $200/month global cap.
#
# Prereqs: the gateway is running (docker compose up -d) and LITELLM_MASTER_KEY is exported
# (e.g. `set -a; . ./.env; set +a`).
#
# Usage:  ./gen-key.sh            # $30/month worker key (well under the $200 global cap)
#         WORKER_MONTHLY_BUDGET=50 ./gen-key.sh

set -euo pipefail

: "${LITELLM_MASTER_KEY:?export LITELLM_MASTER_KEY first (see .env)}"
BASE="${LITELLM_BASE_URL:-http://localhost:4000}"
BUDGET="${WORKER_MONTHLY_BUDGET:-30}"

# No model restriction: a vanilla `claude -p` worker sends arbitrary Claude model IDs, so
# the key must allow the wildcard route. Control is by BUDGET (this key + the $200 global
# cap), not by model allow-list. A future custom orchestrator can use model-scoped keys.
curl -fsS -X POST "$BASE/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"max_budget\": ${BUDGET}, \"budget_duration\": \"1mo\", \"metadata\": {\"role\": \"phase2-worker\"}}"
echo

echo ">> Give the returned key to the worker as its API key, with:"
echo "     ANTHROPIC_BASE_URL=${BASE}"
echo "   The real ANTHROPIC_API_KEY stays only inside the gateway."
