#!/usr/bin/env bash
#
# check-spec-complete.sh — verify a session's SPEC.md has a complete
# `## Impact analysis` subsection (Stakeholders / Components / Data
# dependencies / Side effects, all non-empty) before the design is handed to
# the reviewer agent for Gate A.
#
# WHY THIS EXISTS
#   Impact Analysis enforcement is scripted for deployments (the "not valid
#   if any artifact is empty" rule in #start_guided_deployment) but was
#   review-only on the session side, with no scripted equivalent. This is
#   that equivalent.
#   See work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md §6.
#
# USAGE
#   check-spec-complete.sh <session-id> [--work-sessions-repo <path>]
#
# OPTIONS
#   --work-sessions-repo <path>   Default: sibling ../work-sessions of this
#                                 repo.
#   -h, --help                    Show this help.
#
# Non-zero exit and a listing of the missing/empty field(s) on failure.

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }
needval() { [[ -n "${2:-}" && "${2#-}" == "$2" ]] || die "option '$1' requires a value"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTIC_SDLC_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_SESSIONS_REPO="$(cd "$AGENTIC_SDLC_REPO/.." && pwd)/work-sessions"

SESSION_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)              usage; exit 0 ;;
    --work-sessions-repo)   needval "$@"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    -*)                     die "unknown option: $1 (try --help)" ;;
    *)                      [[ -z "$SESSION_ID" ]] && SESSION_ID="$1" || die "unexpected arg: $1"; shift ;;
  esac
done

[[ -n "$SESSION_ID" ]] || { usage; exit 2; }
[[ -d "$WORK_SESSIONS_REPO" ]] || die "work-sessions repo not found at: $WORK_SESSIONS_REPO (pass --work-sessions-repo)"

SPEC_FILE="$WORK_SESSIONS_REPO/sessions/$SESSION_ID/SPEC.md"

SPEC_FILE_ENV="$SPEC_FILE" python3 "$SCRIPT_DIR/lib/check_spec_complete.py"
