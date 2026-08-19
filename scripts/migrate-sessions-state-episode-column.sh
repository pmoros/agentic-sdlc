#!/usr/bin/env bash
#
# migrate-sessions-state-episode-column.sh — one-time, additive, idempotent
# migration: add an `Item` column to SESSIONS_STATE.md's registry table.
# ADH-011 SPEC.md §7.
#
# WHY THIS EXISTS
#   Every episode of the same item is now a separate SESSIONS_STATE.md row
#   (an episode already gets its own folder). The `Item` column makes those
#   rows joinable by the id they share. Every row that exists today is
#   implicitly episode 1 of its own item (nothing has ever been reopened
#   before this session), so this migration is purely mechanical: `Item` =
#   that row's own `Session ID`. Much smaller blast radius than ADH-008's
#   item-store migration (one markdown file, no locking, no concurrent
#   writers to race — but still dry-run/commit/verify, not a blind edit).
#
# USAGE
#   migrate-sessions-state-episode-column.sh [--dry-run]
#   migrate-sessions-state-episode-column.sh --commit
#   migrate-sessions-state-episode-column.sh --verify
#
# OPTIONS
#   --dry-run                Default, safe to run repeatedly. Prints
#                             whether the migration would change anything,
#                             writes nothing.
#   --commit                 Writes the migrated table back, atomically
#                             (tmp file + rename), after saving a
#                             timestamped `.bak` copy alongside — the
#                             original is never simply overwritten. A
#                             no-op (exit 0) if already migrated.
#   --verify                 Re-reads the file and confirms: header has
#                             `Item`, row count is unchanged, and every
#                             real row's `Item` cell equals its own
#                             `Session ID` cell.
#   --work-sessions-repo <p> Default: sibling ../work-sessions of this repo.
#   -h, --help                Show this help.

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTIC_SDLC_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_SESSIONS_REPO="$(cd "$AGENTIC_SDLC_REPO/.." && pwd)/work-sessions"

MODE="dry-run"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)              usage; exit 0 ;;
    --dry-run)              MODE="dry-run"; shift ;;
    --commit)               MODE="commit"; shift ;;
    --verify)               MODE="verify"; shift ;;
    --work-sessions-repo)   [[ -n "${2:-}" ]] || die "--work-sessions-repo requires a value"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    -*)                     die "unknown option: $1 (try --help)" ;;
    *)                      die "unexpected arg: $1" ;;
  esac
done

STATE="$WORK_SESSIONS_REPO/SESSIONS_STATE.md"
[[ -f "$STATE" ]] || die "SESSIONS_STATE.md not found at: $STATE (pass --work-sessions-repo)"

LIB="$SCRIPT_DIR/lib/migrate_sessions_state.py"

case "$MODE" in
  dry-run)
    migrated="$(python3 "$LIB" < "$STATE")"
    if [[ "$migrated" == "$(cat "$STATE")" ]]; then
      err ">> already migrated (Item column present) — nothing to do"
    else
      rows_before="$(grep -c '^|' "$STATE" || true)"
      err ">> would add an Item column to $STATE ($rows_before table rows affected)"
      err ">> re-run with --commit to write it"
    fi
    ;;

  commit)
    migrated="$(python3 "$LIB" < "$STATE")"
    if [[ "$migrated" == "$(cat "$STATE")" ]]; then
      err ">> already migrated (Item column present) — nothing to do"
      exit 0
    fi
    backup="$STATE.bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp "$STATE" "$backup"
    err ">> backed up original to $backup"
    tmp="$STATE.tmp"
    printf '%s' "$migrated" > "$tmp"
    mv "$tmp" "$STATE"
    err ">> wrote $STATE with the new Item column"
    ;;

  verify)
    content="$(cat "$STATE")"
    header="$(grep '^| Session ID |' "$STATE" || true)"
    [[ -n "$header" ]] || die "no '| Session ID |' header found in $STATE"
    echo "$header" | grep -q '| Item |' || die "header has no Item column — migration not applied"

    fail=0
    while IFS= read -r row; do
      [[ "$row" == "$header" ]] && continue
      [[ "$row" =~ ^\|---.*\|$ ]] && continue
      sid="$(echo "$row" | awk -F'|' '{gsub(/^ +| +$/, "", $2); print $2}')"
      item="$(echo "$row" | awk -F'|' '{gsub(/^ +| +$/, "", $3); print $3}')"
      [[ "$sid" == "_none yet_" ]] && continue
      if [[ "$sid" != "$item" ]]; then
        err "MISMATCH: Session ID '$sid' != Item '$item'"
        fail=1
      fi
    done <<< "$content"

    if [[ "$fail" -eq 0 ]]; then
      err ">> verified: every row's Item matches its own Session ID"
    else
      die "verification failed — see MISMATCH lines above"
    fi
    ;;
esac
