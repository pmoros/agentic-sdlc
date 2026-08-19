#!/usr/bin/env bash
#
# regenerate-views.sh — regenerate the derived, read-only partition views
# (work/backlog.json, work/wip.json, work/archive.json) from
# work/items/*.json. Never invoked or edited manually otherwise.
#
# WHY THIS EXISTS
#   backlog/wip/archive stop being the writable store (that's
#   work/items/<id>.json, one file per item — see define-work-item.sh) and
#   become generated indexes over item `status`. This is what removes the
#   "keep 3 views in agreement" manual-sync rule the old model needed.
#   See work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md §2.
#
#   work/scratchpad.json is explicitly out of scope — a separate,
#   manually-edited, pre-item store (SPEC.md Constraints) — and is never
#   touched here.
#
# USAGE
#   regenerate-views.sh [--check] [--work-sessions-repo <path>]
#
# OPTIONS
#   --check                  Don't write anything. Compare what regeneration
#                            WOULD produce against the views on disk; exit
#                            non-zero (CI-style: fail the build, not a
#                            warning) if they've drifted — a hand-edit or a
#                            writer bug, either way surfaced loudly rather
#                            than silently tolerated.
#   --work-sessions-repo <p> Default: sibling ../work-sessions of this repo.
#   -h, --help               Show this help.

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }
needval() { [[ -n "${2:-}" && "${2#-}" == "$2" ]] || die "option '$1' requires a value"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTIC_SDLC_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_SESSIONS_REPO="$(cd "$AGENTIC_SDLC_REPO/.." && pwd)/work-sessions"

CHECK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)              usage; exit 0 ;;
    --check)                 CHECK=1; shift ;;
    --work-sessions-repo)    needval "$@"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    -*)                      die "unknown option: $1 (try --help)" ;;
    *)                       die "unexpected arg: $1" ;;
  esac
done

[[ -d "$WORK_SESSIONS_REPO" ]] || die "work-sessions repo not found at: $WORK_SESSIONS_REPO (pass --work-sessions-repo)"

WORK_DIR="$WORK_SESSIONS_REPO/work"
mkdir -p "$WORK_DIR/items"

ITEMS_DIR_ENV="$WORK_DIR/items" \
BACKLOG_JSON_ENV="$WORK_DIR/backlog.json" \
WIP_JSON_ENV="$WORK_DIR/wip.json" \
ARCHIVE_JSON_ENV="$WORK_DIR/archive.json" \
CHECK_ENV="$CHECK" \
python3 "$SCRIPT_DIR/lib/regenerate_views.py"
