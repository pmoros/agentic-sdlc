#!/usr/bin/env bash
#
# session-log.sh — append a timestamped line to a session's log(s) in
# work-sessions, with one consistent format. Backs the
# "append to WORKLOG / CONTEXT activity log" step used all over the session
# rules and lifecycle commands, so the timestamp/format never drifts.
#
# Line format: - <YYYY-MM-DD HH:MM> <message>
#   WORKLOG.md          — appended at end (append-only lifetime event log)
#   CONTEXT.md          — appended at end, under its final `## Activity log`
#
# USAGE
#   session-log.sh <session-id> <message> [--to worklog|context|both]
#                                          [--work-sessions-repo <path>]
#
# OPTIONS
#   --to <target>              worklog | context | both  (default: both)
#   --work-sessions-repo <p>   default: sibling ../work-sessions
#   -h, --help                 Show this help.
#
# Autonomous per the Git Policy (session file read/write needs no approval).

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }
needval() { [[ -n "${2:-}" && "${2#-}" == "$2" ]] || die "option '$1' requires a value"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_SESSIONS_REPO="$(cd "$AGENTIC_ROOT/.." && pwd)/work-sessions"
TO="both"
SESSION_ID=""
MESSAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)            usage; exit 0 ;;
    --to)                 needval "$@"; TO="$2"; shift 2 ;;
    --work-sessions-repo) needval "$@"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    -*)                   die "unknown option: $1 (try --help)" ;;
    *)
      if [[ -z "$SESSION_ID" ]]; then SESSION_ID="$1"
      elif [[ -z "$MESSAGE" ]]; then MESSAGE="$1"
      else die "unexpected arg: $1"; fi
      shift ;;
  esac
done

[[ -n "$SESSION_ID" && -n "$MESSAGE" ]] || { usage; die "need <session-id> and <message>"; }
case "$TO" in worklog|context|both) ;; *) die "--to must be worklog|context|both" ;; esac

SESSION_DIR="$WORK_SESSIONS_REPO/sessions/$SESSION_ID"
[[ -d "$SESSION_DIR" ]] || die "session folder not found: $SESSION_DIR"

TS="$(date '+%Y-%m-%d %H:%M')"
LINE="- $TS $MESSAGE"

if [[ "$TO" == "worklog" || "$TO" == "both" ]]; then
  printf '%s\n' "$LINE" >> "$SESSION_DIR/WORKLOG.md"
fi
if [[ "$TO" == "context" || "$TO" == "both" ]]; then
  # CONTEXT.md's `## Activity log` is the final section, so appending at EOF
  # keeps entries under it (matches init-session.sh's convention).
  [[ -f "$SESSION_DIR/CONTEXT.md" ]] || die "CONTEXT.md not found in $SESSION_DIR"
  printf '%s\n' "$LINE" >> "$SESSION_DIR/CONTEXT.md"
fi

err ">> logged to $TO: $LINE"
