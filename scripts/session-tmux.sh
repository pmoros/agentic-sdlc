#!/usr/bin/env bash
#
# session-tmux.sh — guarded tmux lifecycle for work sessions. One place for
# the tmux plumbing that init/resume/stop/end share, so nothing re-inlines it.
#
# Every session is linked to a tmux session named `cw-<session-id>`. These
# helpers are non-interactive-safe: they NEVER run `tmux attach` (that needs a
# TTY and would fail/hang when called by the agent). `attach-hint` just prints
# the command for the user to run themselves (e.g. via a `! ` prompt).
#
# All subcommands degrade gracefully: if tmux isn't installed they print a note
# and exit 0, so a tmux hiccup never fails the surrounding session operation.
#
# USAGE
#   session-tmux.sh name        <session-id>            # print the tmux name
#   session-tmux.sh ensure      <session-id> [workdir]  # create (detached) if missing
#   session-tmux.sh attach-hint <session-id>            # print the attach command
#   session-tmux.sh kill        <session-id>            # kill if present
#   session-tmux.sh exists      <session-id>            # exit 0 if session exists

set -euo pipefail

err() { printf '%s\n' "$*" >&2; }

sub="${1:-}"; sid="${2:-}"; workdir="${3:-}"
[[ -n "$sub" && -n "$sid" ]] || { err "usage: session-tmux.sh {name|ensure|attach-hint|kill|exists} <session-id> [workdir]"; exit 2; }

name="cw-${sid}"

# `name` works without tmux; everything else needs the binary.
if [[ "$sub" == "name" ]]; then
  printf '%s\n' "$name"; exit 0
fi

if ! command -v tmux >/dev/null 2>&1; then
  err "note: tmux not installed — skipping tmux $sub for $name"
  exit 0
fi

case "$sub" in
  exists)
    tmux has-session -t "=$name" 2>/dev/null
    ;;
  ensure)
    if tmux has-session -t "=$name" 2>/dev/null; then
      err ">> tmux session $name already exists"
    else
      if [[ -n "$workdir" && -d "$workdir" ]]; then
        tmux new-session -d -s "$name" -c "$workdir"
      else
        tmux new-session -d -s "$name"
      fi
      err ">> created detached tmux session $name${workdir:+ (cwd: $workdir)}"
    fi
    # Load the session .env into the tmux session env so panes inherit the
    # session's AWS profile/region (and CLAUDE_CODE_DONT_INHERIT_ENV). Idempotent.
    if [[ -n "$workdir" && -f "$workdir/.env" ]]; then
      while IFS= read -r line; do
        line="${line%%#*}"                       # strip comments
        [[ "$line" == *=* ]] || continue          # only KEY=VALUE lines
        key="${line%%=*}"; val="${line#*=}"
        key="${key//[[:space:]]/}"                # squeeze all whitespace in key
        [[ -n "$key" ]] || continue
        val="${val#"${val%%[![:space:]]*}"}"      # ltrim value
        val="${val%"${val##*[![:space:]]}"}"      # rtrim value (keeps inner spaces)
        [[ "$val" == \"*\" && "$val" != '"' ]] && val="${val%\"}" && val="${val#\"}"  # unquote "
        [[ "$val" == \'*\' && "$val" != "'" ]] && val="${val%\'}" && val="${val#\'}"  # unquote '
        tmux set-environment -t "=$name" "$key" "$val"
      done < "$workdir/.env"
      err ">> loaded $workdir/.env into tmux env for $name"
    fi
    err "   attach with:  tmux attach -t $name"
    ;;
  attach-hint)
    if tmux has-session -t "=$name" 2>/dev/null; then
      err ">> attach with:  tmux attach -t $name"
    else
      err ">> tmux session $name does not exist (run: session-tmux.sh ensure $sid)"
    fi
    ;;
  kill)
    if tmux has-session -t "=$name" 2>/dev/null; then
      tmux kill-session -t "=$name"
      err ">> killed tmux session $name"
    else
      err ">> no tmux session $name to kill"
    fi
    ;;
  *)
    err "unknown subcommand: $sub"; exit 2 ;;
esac
