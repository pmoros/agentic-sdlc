#!/usr/bin/env bash
#
# run-worker.sh — run ONE autonomous worker task and capture the FULL
# reasoning/action trace (fixing the earlier gap where `--output-format json`
# saved only the final result).
#
# TWO LANES (ADH-003 subscription pivot, D1/D5):
#   LANE=subscription (default) — Max-plan OAuth via the Keychain. NO API
#     credentials in the process env: the invocation scrubs the COMPLETE
#     documented auth-precedence chain (D5) so a key lingering in the caller's
#     shell can never silently flip the lane back to billing. Constraint =
#     rate-limit windows; cost_basis=estimated. Skips the gateway entirely.
#   LANE=api — the LiteLLM gateway path: the worker gets a budget-capped VIRTUAL
#     key and never sees the raw Anthropic key ($200/mo cap enforced at the
#     gateway). cost_basis=billed. Byte-for-byte the pre-pivot behaviour.
#
# USAGE
#   autonomous-workflows/run-worker.sh <task-id> "<prompt>"            # inline prompt
#   autonomous-workflows/run-worker.sh <task-id> @path/to/prompt.md    # prompt from a file
#   LANE=api BUDGET=5 MODEL=claude-sonnet-5 autonomous-workflows/run-worker.sh t3 @files/task.md
#
# ENV (optional): LANE (subscription|api; default subscription), ROLE
#   (planner|coder|classifier — or a task type like fix/design/research/triage —
#   resolved to a model via routing.py; default coder=Sonnet 5), MODEL (explicit
#   override, wins over ROLE), BUDGET (api-lane USD/mo key cap, default 5),
#   WORKER_TOOLS (allowed-tools list), GATEWAY, RUN_RECORDS_DIR (output dir
#   override; default <parent>/run-records).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # .../autonomous-workflows
SESS="$(dirname "$HERE")"                               # subsystem parent (repo root)
GW="$HERE/gateway"
GATEWAY="${GATEWAY:-http://localhost:4000}"
BUDGET="${BUDGET:-5}"
ROLE="${ROLE:-}"
LANE="${LANE:-subscription}"                            # D1: subscription is the default
MIN_CLI="2.1.211"                                       # Keychain refresh coordination (D5)
OUT_DIR="${RUN_RECORDS_DIR:-$SESS/run-records}"         # overridable (tests)

# Task-based model selection (ADR-001 tiering) via routing.py. An explicit MODEL
# always overrides; otherwise ROLE (or a task type) picks the model; else default.
if [ -z "${MODEL:-}" ]; then
  if [ -n "$ROLE" ]; then MODEL="$(python3 "$HERE/routing.py" "$ROLE")"; else MODEL="claude-sonnet-5"; fi
fi
TOOLS="${WORKER_TOOLS:-Read,Write,Edit,Bash,Glob,Grep,WebSearch,WebFetch}"

TASK_ID="${1:?usage: run-worker.sh <task-id> <prompt-or-@file>}"
PROMPT_IN="${2:?need a prompt (inline string, or @path for a file)}"
case "$PROMPT_IN" in
  @*) PROMPT="$(cat "${PROMPT_IN#@}")" ;;
  *)  PROMPT="$PROMPT_IN" ;;
esac

# --- subscription-lane pre-flight helpers (D5) --------------------------------
_ver_ge() {  # _ver_ge A B  ->  0 (true) iff version A >= version B, componentwise numeric
  local i x y; local -a a b
  IFS=. read -ra a <<<"$1"
  IFS=. read -ra b <<<"$2"
  for i in 0 1 2; do
    x="${a[$i]:-0}"; y="${b[$i]:-0}"
    if   ((10#$x > 10#$y)); then return 0
    elif ((10#$x < 10#$y)); then return 1; fi
  done
  return 0
}

_apikeyhelper_configured() {  # 0 (true) iff apiKeyHelper is set in any settings scope
  local f
  for f in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json" \
           "$PWD/.claude/settings.json" "$PWD/.claude/settings.local.json"; do
    [ -f "$f" ] || continue
    if python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
sys.exit(0 if d.get("apiKeyHelper") else 1)' "$f"; then
      return 0
    fi
  done
  return 1
}

# --- lane setup ---------------------------------------------------------------
if [ "$LANE" = "subscription" ]; then
  COST_BASIS="estimated"
  # Version pre-flight — numeric, componentwise (a string compare passes "2.1.3" > "2.1.211").
  CLI_VER="$(claude --version 2>/dev/null | grep -oE '[0-9]+(\.[0-9]+)+' | head -1 || true)"
  if [ -z "$CLI_VER" ] || ! _ver_ge "$CLI_VER" "$MIN_CLI"; then
    echo "run-worker: subscription lane needs claude >= $MIN_CLI (found ${CLI_VER:-none})" >&2
    exit 1
  fi
  # Settings pre-flight — env -u cannot scrub a *setting*, so refuse to launch if
  # apiKeyHelper is configured (it would silently mint an API key -> real billing).
  if _apikeyhelper_configured; then
    echo "run-worker: subscription lane aborted — apiKeyHelper is configured in a settings scope (would silently bill). Remove it or use LANE=api." >&2
    exit 1
  fi
  echo "run-worker: lane=subscription (Max plan; no API credentials in env) model=$MODEL" >&2
else
  COST_BASIS="billed"
  [ -f "$GW/.env" ] || { echo "run-worker: $GW/.env missing (gateway not set up)" >&2; exit 1; }
  set -a; . "$GW/.env"; set +a
  # Mint a budget-capped virtual key for this run (never printed).
  KEYJSON="$(WORKER_MONTHLY_BUDGET="$BUDGET" LITELLM_BASE_URL="$GATEWAY" bash "$GW/gen-key.sh" 2>/dev/null)"
  WKEY="$(printf '%s' "$KEYJSON" | python3 -c 'import sys,json
for l in sys.stdin:
    l=l.strip()
    if l.startswith("{"):
        print(json.loads(l).get("key","")); break')"
  [ -n "$WKEY" ] || { echo "run-worker: failed to mint a worker key (is the gateway up?)" >&2; exit 1; }
  echo "run-worker: lane=api role=${ROLE:-default} model=$MODEL budget=\$$BUDGET/mo" >&2
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$OUT_DIR/traces"
TRACE="$OUT_DIR/traces/${TASK_ID}-${TS}.jsonl"
RESULT="$OUT_DIR/traces/${TASK_ID}-${TS}.result.json"
echo "run-worker: trace -> $TRACE" >&2

# --- invocation (lane-selected env) ------------------------------------------
# stream-json emits every event; tee saves the whole stream, the python filter
# writes the final `result` event (augmented with the lane/record fields) for the
# run-record.
run_subscription() {
  # Complete auth-precedence scrub (D5): 7 credential vars + endpoint hygiene.
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN \
      -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_USE_BEDROCK -u CLAUDE_CODE_USE_VERTEX \
      -u CLAUDE_CODE_USE_FOUNDRY -u CLAUDE_CODE_USE_MANTLE \
      ANTHROPIC_MODEL="$MODEL" \
    claude -p "$PROMPT" \
      --output-format stream-json --verbose \
      --permission-mode acceptEdits \
      --allowed-tools "$TOOLS" \
      --add-dir "$SESS" < /dev/null
}
run_api() {
  ANTHROPIC_BASE_URL="$GATEWAY" ANTHROPIC_API_KEY="$WKEY" ANTHROPIC_MODEL="$MODEL" \
    claude -p "$PROMPT" \
      --output-format stream-json --verbose \
      --permission-mode acceptEdits \
      --allowed-tools "$TOOLS" \
      --add-dir "$SESS" < /dev/null
}

if [ "$LANE" = "subscription" ]; then run_subscription; else run_api; fi \
  | tee "$TRACE" \
  | LANE="$LANE" COST_BASIS="$COST_BASIS" TASK_ID="$TASK_ID" MODEL="$MODEL" STARTED_AT="$STARTED_AT" \
    python3 -c 'import sys,json,os
last={}
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    try: o=json.loads(line)
    except Exception: continue
    if o.get("type")=="result": last=o
# Merge the lane/record fields onto the result event (D5/D6 post-run).
last.update({
    "task_id":    os.environ.get("TASK_ID"),
    "lane":       os.environ.get("LANE"),
    "cost_basis": os.environ.get("COST_BASIS"),
    "model":      os.environ.get("MODEL"),
    "started_at": os.environ.get("STARTED_AT"),
})
json.dump(last, open(sys.argv[1],"w"), indent=2)' "$RESULT"

echo "run-worker: done (lane=$LANE, cost_basis=$COST_BASIS)." >&2
python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
print("  is_error:", d.get("is_error"), "| turns:", d.get("num_turns"),
      "| lane:", d.get("lane"), "| cost_basis:", d.get("cost_basis"),
      "| cli_cost:", d.get("total_cost_usd"), "| session:", d.get("session_id"))
print("  trace:", sys.argv[2])
print("  NOTE (api lane): authoritative spend = gateway meter, not the CLI cost.")' "$RESULT" "$TRACE"
