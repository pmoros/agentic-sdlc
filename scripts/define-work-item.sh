#!/usr/bin/env bash
#
# define-work-item.sh — the ONE canonical constructor for a Work Item.
#
# WHY THIS EXISTS
#   Today, item-shaping logic is duplicated across #triage-inbox and
#   init-session.sh's upsert path — already diverged (live data uses the
#   field name `scope`, docs/template say `weight`). This is the single
#   writing mechanism for work/items/<id>.json; every caller that creates or
#   reshapes an item goes through it instead of duplicating shaping logic.
#   See work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md §1, §3.
#
# LOCKING
#   Each item gets its own `work/items/<id>.json.lock/` mutex, acquired via
#   atomic `mkdir` (portable — no `flock` binary dependency). A lock is only
#   force-broken when BOTH the lock is older than the stale threshold AND
#   the recorded holder PID is confirmed dead (`kill -0`) — a legitimately
#   slow but still-alive writer is never preempted. Single-machine liveness
#   check only; cross-machine/networked locking is out of scope.
#
# USAGE
#   define-work-item.sh <id> --title <t> --description <d> --status <s>
#     [--priority <p>] [--scope <XS|S|M|L|XL>] [--ticket <id-or-url>]
#     [--task-type <type>] [--work-sessions-repo <path>]
#
# OPTIONS
#   --title <t>                   Item title. New item: seeded from
#                                 --description (+ --task-type) if omitted.
#                                 Existing item: left unchanged if omitted.
#   --description <d>             Item description.
#   --status <s>                  grooming|ready|in progress|on hold|
#                                 in review|done. New item defaults to
#                                 `grooming`.
#   --priority <p>                Jira priority scale value.
#   --scope <XS|S|M|L|XL>         Effort estimate.
#   --ticket <id-or-url>          Merged into the item's `tickets` map under
#                                 the `main-bug-tracking` label.
#   --task-type <type>            feat|fix|chore|refactor|docs|spike — used
#                                 only to seed a new item's title.
#   --work-sessions-repo <path>   Default: sibling ../work-sessions of this
#                                 repo.
#   -h, --help                    Show this help.
#
# Only fields explicitly passed change; everything else on an existing item
# (including sessions[], history, current_state, roadmap) is preserved.
# `current_state`/`history`/`sessions` are owned by the session lifecycle,
# not this constructor — it only initializes them for a brand new item.
#
# ENV (test/tuning hooks — production defaults are fine as-is)
#   DEFINE_ITEM_LOCK_TIMEOUT_SECS   Max seconds to wait for the lock. Default: 10.
#   DEFINE_ITEM_LOCK_STALE_SECS     Lock age before a dead-PID lock is
#                                   eligible to be broken. Default: 60.

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }
needval() { [[ -n "${2:-}" && "${2#-}" == "$2" ]] || die "option '$1' requires a value"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTIC_SDLC_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_SESSIONS_REPO="$(cd "$AGENTIC_SDLC_REPO/.." && pwd)/work-sessions"

ITEM_ID=""
TITLE=""
DESCRIPTION=""
STATUS=""
PRIORITY=""
SCOPE=""
TICKET=""
TASK_TYPE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)              usage; exit 0 ;;
    --title)                needval "$@"; TITLE="$2"; shift 2 ;;
    --description)           needval "$@"; DESCRIPTION="$2"; shift 2 ;;
    --status)                needval "$@"; STATUS="$2"; shift 2 ;;
    --priority)               needval "$@"; PRIORITY="$2"; shift 2 ;;
    --scope)                  needval "$@"; SCOPE="$2"; shift 2 ;;
    --ticket)                 needval "$@"; TICKET="$2"; shift 2 ;;
    --task-type)              needval "$@"; TASK_TYPE="$2"; shift 2 ;;
    --work-sessions-repo)     needval "$@"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    -*)                       die "unknown option: $1 (try --help)" ;;
    *)                        [[ -z "$ITEM_ID" ]] && ITEM_ID="$1" || die "unexpected arg: $1"; shift ;;
  esac
done

[[ -n "$ITEM_ID" ]] || { usage; exit 2; }
[[ -d "$WORK_SESSIONS_REPO" ]] || die "work-sessions repo not found at: $WORK_SESSIONS_REPO (pass --work-sessions-repo)"

ITEMS_DIR="$WORK_SESSIONS_REPO/work/items"
mkdir -p "$ITEMS_DIR"
ITEM_FILE="$ITEMS_DIR/$ITEM_ID.json"
LOCK_DIR="$ITEM_FILE.lock"

TIMEOUT="${DEFINE_ITEM_LOCK_TIMEOUT_SECS:-10}"
STALE_AFTER="${DEFINE_ITEM_LOCK_STALE_SECS:-60}"

# lock_dir_mtime <path> — portable directory mtime (seconds since epoch).
lock_dir_mtime() {
  case "$(uname -s)" in
    Darwin) stat -f %m "$1" 2>/dev/null ;;
    *)      stat -c %Y "$1" 2>/dev/null ;;
  esac
}

LOCK_HELD=0

acquire_lock() {
  local start now_ts holder_pid mtime age
  start="$(date +%s)"
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    holder_pid=""
    [[ -f "$LOCK_DIR/pid" ]] && holder_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    mtime="$(lock_dir_mtime "$LOCK_DIR" || echo "")"
    now_ts="$(date +%s)"
    if [[ -n "$mtime" ]]; then
      age=$(( now_ts - mtime ))
      if [[ "$age" -ge "$STALE_AFTER" && -n "$holder_pid" ]] && ! kill -0 "$holder_pid" 2>/dev/null; then
        err ">> breaking stale lock (holder pid $holder_pid not running, age ${age}s): $LOCK_DIR"
        rm -rf "$LOCK_DIR"
        continue
      fi
    fi
    if (( now_ts - start >= TIMEOUT )); then
      die "timed out after ${TIMEOUT}s waiting for lock on $ITEM_ID (held by pid ${holder_pid:-unknown}): $LOCK_DIR"
    fi
    sleep 0.2
  done
  echo $$ > "$LOCK_DIR/pid"
  LOCK_HELD=1
}

release_lock() {
  [[ "$LOCK_HELD" -eq 1 ]] && rm -rf "$LOCK_DIR"
}
trap release_lock EXIT

acquire_lock

ITEM_ID_ENV="$ITEM_ID" ITEM_FILE_ENV="$ITEM_FILE" \
TITLE_ENV="$TITLE" DESCRIPTION_ENV="$DESCRIPTION" STATUS_ENV="$STATUS" \
PRIORITY_ENV="$PRIORITY" SCOPE_ENV="$SCOPE" TICKET_ENV="$TICKET" \
TASK_TYPE_ENV="$TASK_TYPE" NOW_ENV="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
python3 "$SCRIPT_DIR/lib/define_work_item.py" || die "failed to define item $ITEM_ID"

err ">> wrote $ITEM_FILE"
