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
#   ADH-012: `--parent`/`--promote` additionally acquire a second, SHARED
#   `work/items/.parent-link.lock/` (same mechanism, generalized) before
#   the item's own lock — this serializes every parent-link mutation across
#   the whole item store, closing a real multi-level-chain race that an
#   unguarded validation read would otherwise allow between two DIFFERENT
#   items' concurrent `--parent` calls. See
#   work-sessions/sessions/ADH-012-epic-subitems/SPEC.md §4.
#
# USAGE
#   define-work-item.sh <id> --title <t> --description <d> --status <s>
#     [--priority <p>] [--scope <XS|S|M|L|XL>] [--ticket <id-or-url>]
#     [--task-type <type>] [--record-event <action>] [--by <name>]
#     [--current-state <description>] [--blocked] [--work-sessions-repo <path>]
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
#   --record-event <action>       Explicit opt-in: append one history entry
#                                 {action, timestamp: now, by}. Every other
#                                 flag above only reshapes FIELDS — history/
#                                 current_state/sessions are normally left
#                                 untouched on an existing item, so an
#                                 ordinary shaping call can never clobber
#                                 them. A caller that needs to record a
#                                 discrete event through this same locked
#                                 write path (init-session.sh: "session
#                                 started"; #triage-inbox: "Triaged from
#                                 INBOX") passes this explicitly.
#   --by <name>                   `by` for --record-event. Default:
#                                 define-work-item.sh.
#   --current-state <description> Explicit opt-in: overwrite
#                                 current_state.description (+ is_blocked,
#                                 via --blocked). Same opt-in as --record-event.
#   --blocked                     Sets current_state.is_blocked true. Only
#                                 meaningful with --current-state.
#   --last-synced <ISO8601>       Explicit opt-in: set the `last_synced`
#                                 watermark. #end_work_session's batched
#                                 close-checkpoint records this after a
#                                 successful external-write batch. Never
#                                 reset by an unrelated reshape.
#   --open-episode <session-id>   ADH-011: explicit opt-in. Reopen this item
#                                 as a new episode (session id is normally
#                                 <item-id>--e<N>) — appends to sessions[],
#                                 sets status to "in progress", records a
#                                 "reopened as episode N" history entry.
#                                 Errors if the last episode is still open.
#   --close-episode <session-id>  ADH-011: explicit opt-in, requires
#                                 --outcome. Closes the matching sessions[]
#                                 entry (found by session id); when
#                                 --outcome is "done", also sets the item's
#                                 status to "done". This is how a session
#                                 close reaches "done" post-ADH-008 — no
#                                 other flag does.
#   --outcome <done|stopped|paused>  Required companion to --close-episode.
#   --parent <parent-item-id>     ADH-012: link this item as a sub-item of
#                                 <parent-item-id> (epic-like grouping).
#                                 Validated before any lock is acquired:
#                                 refuses a self-parent, a nonexistent
#                                 target, linking under an item that
#                                 already has a parent, or linking an item
#                                 that's already a parent to something else
#                                 — exactly one level of nesting is
#                                 supported. Mutually exclusive with
#                                 --promote.
#   --promote                     ADH-012: clear this item's parent_id
#                                 (de-aggregate back to independent).
#                                 Refuses if the item has no parent_id to
#                                 clear. Mutually exclusive with --parent.
#   --roadmap-step <text>         ADH-014: append one {step, owner,
#                                 target_date, type} entry to roadmap[]
#                                 (creating it if absent) — append-only,
#                                 same precedent as history. Requires
#                                 --roadmap-owner.
#   --roadmap-owner <name>        Required alongside --roadmap-step.
#   --roadmap-target-date <date>  Optional, only meaningful with
#                                 --roadmap-step. Default: TBD.
#   --roadmap-type <type>         Optional, only meaningful with
#                                 --roadmap-step. Default: standard.
#   --work-sessions-repo <path>   Default: sibling ../work-sessions of this
#                                 repo.
#   -h, --help                    Show this help.
#
# GUARDRAILS (ADH-014)
#   --status done combined with --close-episode (any outcome) is refused
#   at parse time — --close-episode --outcome done already sets status,
#   so passing both is redundant or contradictory.
#
#   --status done WITHOUT --close-episode is refused if the item's
#   sessions[] last entry is still open (closed: null) — use
#   --close-episode --outcome done instead, so the episode record and the
#   item's status move together. This check runs inside the item's own
#   lock, immediately before the write, not as a separate pre-lock read —
#   see the inline comment at the call site for why that ordering matters.
#
# Only fields explicitly passed change; everything else on an existing item
# (including sessions[], history, current_state, roadmap) is preserved.
# `current_state`/`history`/`sessions` are owned by the session lifecycle,
# not this constructor — it only initializes them for a brand new item, or
# when a caller explicitly opts in via --record-event/--current-state.
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
RECORD_EVENT=""
EVENT_BY=""
CURRENT_STATE_DESCRIPTION=""
CURRENT_STATE_BLOCKED=0
LAST_SYNCED=""
OPEN_EPISODE=""
CLOSE_EPISODE=""
OUTCOME=""
PARENT=""
PROMOTE=0
ROADMAP_STEP=""
ROADMAP_OWNER=""
ROADMAP_TARGET_DATE=""
ROADMAP_TYPE=""

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
    --record-event)           needval "$@"; RECORD_EVENT="$2"; shift 2 ;;
    --by)                     needval "$@"; EVENT_BY="$2"; shift 2 ;;
    --current-state)          needval "$@"; CURRENT_STATE_DESCRIPTION="$2"; shift 2 ;;
    --blocked)                CURRENT_STATE_BLOCKED=1; shift ;;
    --last-synced)            needval "$@"; LAST_SYNCED="$2"; shift 2 ;;
    --open-episode)            needval "$@"; OPEN_EPISODE="$2"; shift 2 ;;
    --close-episode)            needval "$@"; CLOSE_EPISODE="$2"; shift 2 ;;
    --outcome)                   needval "$@"; OUTCOME="$2"; shift 2 ;;
    --parent)                     needval "$@"; PARENT="$2"; shift 2 ;;
    --promote)                    PROMOTE=1; shift ;;
    --roadmap-step)                needval "$@"; ROADMAP_STEP="$2"; shift 2 ;;
    --roadmap-owner)                 needval "$@"; ROADMAP_OWNER="$2"; shift 2 ;;
    --roadmap-target-date)             needval "$@"; ROADMAP_TARGET_DATE="$2"; shift 2 ;;
    --roadmap-type)                      needval "$@"; ROADMAP_TYPE="$2"; shift 2 ;;
    --work-sessions-repo)     needval "$@"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    -*)                       die "unknown option: $1 (try --help)" ;;
    *)                        [[ -z "$ITEM_ID" ]] && ITEM_ID="$1" || die "unexpected arg: $1"; shift ;;
  esac
done

[[ -n "$ITEM_ID" ]] || { usage; exit 2; }
[[ -d "$WORK_SESSIONS_REPO" ]] || die "work-sessions repo not found at: $WORK_SESSIONS_REPO (pass --work-sessions-repo)"
[[ -n "$CLOSE_EPISODE" && -z "$OUTCOME" ]] && die "--close-episode requires --outcome <done|stopped|paused>"
[[ -n "$PARENT" && "$PROMOTE" -eq 1 ]] && die "--parent and --promote are mutually exclusive"
[[ "$STATUS" == "done" && -n "$CLOSE_EPISODE" ]] && die "--status done and --close-episode are mutually exclusive — --close-episode --outcome done already sets status to done; passing both is redundant or (with a non-done outcome) contradictory"
[[ -z "$ROADMAP_STEP" && ( -n "$ROADMAP_OWNER" || -n "$ROADMAP_TARGET_DATE" || -n "$ROADMAP_TYPE" ) ]] && die "--roadmap-owner/--roadmap-target-date/--roadmap-type require --roadmap-step"
[[ -n "$ROADMAP_STEP" && -z "$ROADMAP_OWNER" ]] && die "--roadmap-step requires --roadmap-owner"
if [[ -n "$ROADMAP_STEP" ]]; then
  [[ -n "$ROADMAP_TARGET_DATE" ]] || ROADMAP_TARGET_DATE="TBD"
  [[ -n "$ROADMAP_TYPE" ]] || ROADMAP_TYPE="standard"
fi

ITEMS_DIR="$WORK_SESSIONS_REPO/work/items"
mkdir -p "$ITEMS_DIR"
ITEM_FILE="$ITEMS_DIR/$ITEM_ID.json"
LOCK_DIR="$ITEM_FILE.lock"
PARENT_LOCK_DIR="$ITEMS_DIR/.parent-link.lock"

TIMEOUT="${DEFINE_ITEM_LOCK_TIMEOUT_SECS:-10}"
STALE_AFTER="${DEFINE_ITEM_LOCK_STALE_SECS:-60}"

# lock_dir_mtime <path> — portable directory mtime (seconds since epoch).
lock_dir_mtime() {
  case "$(uname -s)" in
    Darwin) stat -f %m "$1" 2>/dev/null ;;
    *)      stat -c %Y "$1" 2>/dev/null ;;
  esac
}

# HELD_LOCKS tracks every lock dir this process currently holds, so a
# single EXIT trap releases all of them (item lock, and — for
# --parent/--promote — the shared parent-link lock too) regardless of how
# many were acquired or in what order.
HELD_LOCKS=()

# acquire_lock <lock_dir> <label> — generalized so both the per-item lock
# and ADH-012's shared parent-link lock use the exact same mkdir-based,
# PID-liveness stale-break mechanism without duplicating it.
acquire_lock() {
  local lock_dir="$1" label="$2"
  local start now_ts holder_pid mtime age
  start="$(date +%s)"
  while ! mkdir "$lock_dir" 2>/dev/null; do
    holder_pid=""
    [[ -f "$lock_dir/pid" ]] && holder_pid="$(cat "$lock_dir/pid" 2>/dev/null || true)"
    mtime="$(lock_dir_mtime "$lock_dir" || echo "")"
    now_ts="$(date +%s)"
    if [[ -n "$mtime" ]]; then
      age=$(( now_ts - mtime ))
      if [[ "$age" -ge "$STALE_AFTER" && -n "$holder_pid" ]] && ! kill -0 "$holder_pid" 2>/dev/null; then
        err ">> breaking stale lock (holder pid $holder_pid not running, age ${age}s): $lock_dir"
        rm -rf "$lock_dir"
        continue
      fi
    fi
    if (( now_ts - start >= TIMEOUT )); then
      die "timed out after ${TIMEOUT}s waiting for $label lock (held by pid ${holder_pid:-unknown}): $lock_dir"
    fi
    sleep 0.2
  done
  echo $$ > "$lock_dir/pid"
  HELD_LOCKS+=("$lock_dir")
}

release_locks() {
  local d
  for d in "${HELD_LOCKS[@]:-}"; do
    [[ -n "$d" ]] && rm -rf "$d"
  done
}
trap release_locks EXIT

# --- ADH-012: validate + serialize a parent-link mutation, before the
# item's own lock is ever acquired -------------------------------------
if [[ -n "$PARENT" ]]; then
  acquire_lock "$PARENT_LOCK_DIR" "parent-link"
  python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/lib')
from define_work_item import validate_parent_link
try:
    validate_parent_link('$ITEMS_DIR', '$ITEM_ID', '$PARENT')
except ValueError as exc:
    print(f'define-work-item: {exc}', file=sys.stderr)
    sys.exit(1)
" || die "parent link validation failed for $ITEM_ID -> $PARENT"
elif [[ "$PROMOTE" -eq 1 ]]; then
  acquire_lock "$PARENT_LOCK_DIR" "parent-link"
  python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/lib')
from define_work_item import validate_promote
try:
    validate_promote('$ITEMS_DIR', '$ITEM_ID')
except ValueError as exc:
    print(f'define-work-item: {exc}', file=sys.stderr)
    sys.exit(1)
" || die "promote validation failed for $ITEM_ID"
fi

acquire_lock "$LOCK_DIR" "item"

# --- ADH-014 Tier 1: refuse --status done while an episode is still open.
# MUST run here — after the item's own lock is held, immediately before
# the write — not as a separately-timed pre-lock read. Gate A round 2:
# a pre-lock read is exactly the unguarded-read hazard
# validate_parent_link's own docstring warns about; once this process
# holds $LOCK_DIR, no concurrent writer can be mid-write on this same
# item, so a read taken now is authoritative, not stale.
if [[ "$STATUS" == "done" && -z "$CLOSE_EPISODE" && -f "$ITEM_FILE" ]]; then
  ITEM_FILE_ENV="$ITEM_FILE" python3 -c "
import json, os, sys
with open(os.environ['ITEM_FILE_ENV']) as fh:
    item = json.load(fh)
sessions = item.get('sessions') or []
if sessions and sessions[-1].get('closed') is None:
    print(
        f\"define-work-item: item has an open episode \"
        f\"({sessions[-1].get('episode_id')!r}) — use --close-episode \"
        f\"<session-id> --outcome done instead of a plain --status done, \"
        f\"to avoid leaving inconsistent episode state\",
        file=sys.stderr,
    )
    sys.exit(1)
" || die "refused: open episode on $ITEM_ID (see message above)"
fi

ITEM_ID_ENV="$ITEM_ID" ITEM_FILE_ENV="$ITEM_FILE" \
TITLE_ENV="$TITLE" DESCRIPTION_ENV="$DESCRIPTION" STATUS_ENV="$STATUS" \
PRIORITY_ENV="$PRIORITY" SCOPE_ENV="$SCOPE" TICKET_ENV="$TICKET" \
TASK_TYPE_ENV="$TASK_TYPE" NOW_ENV="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
RECORD_EVENT_ENV="$RECORD_EVENT" EVENT_BY_ENV="$EVENT_BY" \
CURRENT_STATE_DESCRIPTION_ENV="$CURRENT_STATE_DESCRIPTION" \
CURRENT_STATE_BLOCKED_ENV="$CURRENT_STATE_BLOCKED" \
LAST_SYNCED_ENV="$LAST_SYNCED" \
OPEN_EPISODE_ENV="$OPEN_EPISODE" CLOSE_EPISODE_ENV="$CLOSE_EPISODE" OUTCOME_ENV="$OUTCOME" \
PARENT_ID_ENV="$PARENT" PROMOTE_ENV="$PROMOTE" \
ROADMAP_STEP_ENV="$ROADMAP_STEP" ROADMAP_OWNER_ENV="$ROADMAP_OWNER" \
ROADMAP_TARGET_DATE_ENV="$ROADMAP_TARGET_DATE" ROADMAP_TYPE_ENV="$ROADMAP_TYPE" \
python3 "$SCRIPT_DIR/lib/define_work_item.py" || die "failed to define item $ITEM_ID"

err ">> wrote $ITEM_FILE"

"$SCRIPT_DIR/regenerate-views.sh" --work-sessions-repo "$WORK_SESSIONS_REPO" \
  || die "wrote $ITEM_FILE but regenerate-views.sh failed — views may be stale, re-run it directly"
