#!/usr/bin/env bash
#
# migrate-items-v2.sh — one-time migration from backlog.json/wip.json (the
# old shared-file item store) to work/items/<id>.json (one file per item).
#
# WHY THIS EXISTS
#   The item store is moving from two shared files (backlog.json, wip.json)
#   to one file per item under work/items/, written going forward by
#   define-work-item.sh. This is the one-time step that carries the 7
#   existing sessions' real item data across without loss. See
#   work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md §5.
#
#   work/scratchpad.json is explicitly out of scope (SPEC.md Constraints) —
#   never migrated into an item, only its entry count is noted in --dry-run
#   output as an informational, untouched aside.
#
# USAGE
#   migrate-items-v2.sh [--dry-run]
#   migrate-items-v2.sh --commit
#   migrate-items-v2.sh --commit-cleanup
#   migrate-items-v2.sh --verify
#
# OPTIONS
#   --dry-run                 Default, safe to run repeatedly. Reads
#                              backlog.json/wip.json, writes nothing, prints
#                              a per-item diff of what --commit would
#                              produce and a summary count.
#   --commit                  Refuses if work/items/ already holds a prior
#                              migration (a real, non-staging entry).
#                              Clears a stale work/items/.staging/ left by
#                              an interrupted prior attempt, then writes
#                              every new work/items/<id>.json to a fresh
#                              staging dir, independently re-reads each one
#                              back and verifies it is byte-identical to the
#                              source on every pre-existing field. A single
#                              failing item aborts the WHOLE commit — no
#                              partial work/items/ is ever left visible —
#                              only after every item verifies does it move
#                              staging into place. backlog.json/wip.json are
#                              left in place, untouched, until a human runs
#                              --commit-cleanup.
#   --commit-cleanup           Renames backlog.json/wip.json to
#                              *.pre-migration.bak (never deletes). Run only
#                              after reviewing a successful --commit.
#   --verify                  Standalone verification pass against an
#                              already-committed work/items/ (also runs
#                              automatically at the end of --commit).
#   --work-sessions-repo <p>  Default: sibling ../work-sessions of this repo.
#   -h, --help                 Show this help.
#
# ENV (test-only hook — production runs never set this)
#   MIGRATE_FAULT_CORRUPT_ID_ENV   During --commit, deliberately corrupts the
#                                  named item's staged write before the
#                                  verification re-read, to exercise the
#                                  single-failing-item-aborts-the-whole-
#                                  commit contract end-to-end in tests.

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }
needval() { [[ -n "${2:-}" && "${2#-}" == "$2" ]] || die "option '$1' requires a value"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTIC_SDLC_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_SESSIONS_REPO="$(cd "$AGENTIC_SDLC_REPO/.." && pwd)/work-sessions"

MODE="dry-run"
MODE_SET=0

set_mode() {
  [[ "$MODE_SET" -eq 0 ]] || die "only one of --dry-run/--commit/--commit-cleanup/--verify may be given"
  MODE="$1"
  MODE_SET=1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)               usage; exit 0 ;;
    --dry-run)                set_mode "dry-run"; shift ;;
    --commit)                 set_mode "commit"; shift ;;
    --commit-cleanup)         set_mode "commit-cleanup"; shift ;;
    --verify)                 set_mode "verify"; shift ;;
    --work-sessions-repo)     needval "$@"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    -*)                       die "unknown option: $1 (try --help)" ;;
    *)                        die "unexpected arg: $1" ;;
  esac
done

[[ -d "$WORK_SESSIONS_REPO" ]] || die "work-sessions repo not found at: $WORK_SESSIONS_REPO (pass --work-sessions-repo)"

WORK_DIR="$WORK_SESSIONS_REPO/work"
[[ -d "$WORK_DIR" ]] || die "no work/ directory found at: $WORK_DIR"

MODE_ENV="$MODE" WORK_DIR_ENV="$WORK_DIR" WORK_SESSIONS_REPO_ENV="$WORK_SESSIONS_REPO" \
python3 "$SCRIPT_DIR/lib/migrate_items.py"
