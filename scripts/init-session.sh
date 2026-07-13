#!/usr/bin/env bash
#
# init-session.sh — create a new session folder in work-sessions
# from session-template/, register it in SESSIONS_STATE.md, and set up the
# mandatory, always-present detached worktree of this repo (agentic-sdlc)
# inside the session's worktrees/ folder.
#
# Backs the `initialize_work_session_folder` command. Does NOT create
# target-repo worktrees — that's scripts/create-worktree.sh, invoked
# separately (once per target repo) by the `create_work_tree` command.
#
# USAGE
#   init-session.sh <session-id-slug> --goal "<one-line goal>" [options]
#
# OPTIONS
#   --goal <text>                Required. One-line goal, recorded in
#                                CONTEXT.md's Overview and Current State
#                                Description (unless --blockers is given).
#   --ticket <id-or-url>          Ticket id/URL, recorded in the Tickets table.
#   --scope <XS|S|M|L|XL>         Recorded in the Overview line.
#   --task-type <type>            feat|fix|chore|refactor|docs|spike —
#                                recorded in the Overview line.
#   --blockers <text>             Sets Blocked: yes + this description
#                                instead of --goal. Default: Blocked: no.
#   --work-sessions-repo <path>   Default: sibling
#                                ../work-sessions of this repo.
#   --agentic-sdlc-repo <path>    Default: this script's repo root.
#   -h, --help                    Show this help.
#
# EXAMPLES
#   scripts/init-session.sh PROJ-1234-fix-thing \
#     --goal "Fix the thing" --ticket https://yourcompany.atlassian.net/browse/PROJ-1234 \
#     --scope M --task-type fix
#   scripts/init-session.sh ADH-007-explore-x --goal "Explore x" --scope S --task-type spike
#
# See docs/create-worktree.md for how the agentic-sdlc worktree this script
# creates is kept in sync on resume.

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }

needval() { [[ -n "${2:-}" && "${2#-}" == "$2" ]] || die "option '$1' requires a value"; }

# sed_repl <text> — escape a string for safe use as sed replacement text
# with delimiter '#' (escapes backslash, ampersand, and the delimiter).
sed_repl() { printf '%s' "$1" | sed -e 's/[\&#]/\\&/g'; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTIC_SDLC_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_SESSIONS_REPO="$(cd "$AGENTIC_SDLC_REPO/.." && pwd)/work-sessions"

SESSION_ID=""
GOAL=""
TICKET=""
SCOPE=""
TASK_TYPE=""
BLOCKERS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)             usage; exit 0 ;;
    --goal)                needval "$@"; GOAL="$2"; shift 2 ;;
    --ticket)               needval "$@"; TICKET="$2"; shift 2 ;;
    --scope)                needval "$@"; SCOPE="$2"; shift 2 ;;
    --task-type)            needval "$@"; TASK_TYPE="$2"; shift 2 ;;
    --blockers)              needval "$@"; BLOCKERS="$2"; shift 2 ;;
    --work-sessions-repo)   needval "$@"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    --agentic-sdlc-repo)    needval "$@"; AGENTIC_SDLC_REPO="$2"; shift 2 ;;
    -*)                     die "unknown option: $1 (try --help)" ;;
    *)                      [[ -z "$SESSION_ID" ]] && SESSION_ID="$1" || die "unexpected arg: $1"; shift ;;
  esac
done

[[ -n "$SESSION_ID" ]] || { usage; exit 2; }
[[ -n "$GOAL" ]] || die "--goal is required"
[[ -d "$WORK_SESSIONS_REPO/.git" ]] || die "work-sessions repo not found at: $WORK_SESSIONS_REPO (pass --work-sessions-repo)"
[[ -d "$AGENTIC_SDLC_REPO/.git" ]] || die "agentic-sdlc repo not found at: $AGENTIC_SDLC_REPO (pass --agentic-sdlc-repo)"

TEMPLATE_DIR="$WORK_SESSIONS_REPO/session-template"
[[ -d "$TEMPLATE_DIR" ]] || die "session-template not found at: $TEMPLATE_DIR"

SESSION_DIR="$WORK_SESSIONS_REPO/sessions/$SESSION_ID"
[[ -e "$SESSION_DIR" ]] && die "session folder already exists: $SESSION_DIR"

err ">> creating session folder: $SESSION_DIR"
mkdir -p "$(dirname "$SESSION_DIR")"
cp -R "$TEMPLATE_DIR" "$SESSION_DIR"
mkdir -p "$SESSION_DIR/worktrees"

# --- generate the session .env (local, gitignored) ---------------------
# Every session gets AWS defaults so Claude, the AWS MCP server, and the CLI
# all target the same profile/region. session-tmux.sh loads this into the
# session's tmux env; scripts/aws-login.sh reads it to (re)authenticate.
ENV_FILE="$SESSION_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'ENVEOF'
# Session AWS environment — local & machine-specific (gitignored).
# See .env.example for the documented shape. Edit per session as needed.

# Default profile Claude, the AWS MCP server, and the CLI use for this session.
AWS_PROFILE=cw-test

# Default region for all AWS calls.
AWS_DEFAULT_REGION=us-east-1

# Profiles this session is allowed to switch to / authenticate (comma-separated).
# scripts/aws-login.sh (and #aws-reauth) refuse any profile not listed here.
AWS_ALLOWED_PROFILES=cw-test,cw-partner

# Prevent Claude Code from inheriting AWS_* / other profiles from your broader
# login shell, so a stray AWS_PROFILE there can't override the session default.
CLAUDE_CODE_DONT_INHERIT_ENV=true
ENVEOF
  err ">> wrote session .env (AWS_PROFILE=cw-test, region us-east-1)"
fi

# --- fill in CONTEXT.md ------------------------------------------------
CONTEXT="$SESSION_DIR/CONTEXT.md"
TODAY="$(date +%Y-%m-%d)"
NOW="$(date '+%Y-%m-%d %H:%M')"

OVERVIEW_LINE="$GOAL"
[[ -n "$TASK_TYPE" ]] && OVERVIEW_LINE="[$TASK_TYPE] $OVERVIEW_LINE"
[[ -n "$SCOPE" ]] && OVERVIEW_LINE="$OVERVIEW_LINE (scope: $SCOPE)"

sed "s#<!-- What is this session about, in 2-3 sentences. -->#$(sed_repl "$OVERVIEW_LINE")#" \
  "$CONTEXT" > "$CONTEXT.tmp" && mv "$CONTEXT.tmp" "$CONTEXT"

if [[ -n "$TICKET" ]]; then
  sed "s#| main | |#| main | $(sed_repl "$TICKET") |#" "$CONTEXT" > "$CONTEXT.tmp" && mv "$CONTEXT.tmp" "$CONTEXT"
fi

if [[ -n "$BLOCKERS" ]]; then
  sed 's#- \*\*Blocked:\*\* no#- **Blocked:** yes#' "$CONTEXT" > "$CONTEXT.tmp" && mv "$CONTEXT.tmp" "$CONTEXT"
  sed "s#- \*\*Description:\*\* #- **Description:** $(sed_repl "$BLOCKERS")#" "$CONTEXT" > "$CONTEXT.tmp" && mv "$CONTEXT.tmp" "$CONTEXT"
else
  sed "s#- \*\*Description:\*\* #- **Description:** $(sed_repl "$GOAL")#" "$CONTEXT" > "$CONTEXT.tmp" && mv "$CONTEXT.tmp" "$CONTEXT"
fi

# tmux session name (single source of truth: session-tmux.sh).
TMUX_NAME="$("$SCRIPT_DIR/session-tmux.sh" name "$SESSION_ID")"

printf -- '- %s session initialized (tmux: %s)\n' "$NOW" "$TMUX_NAME" >> "$CONTEXT"

# --- register in SESSIONS_STATE.md --------------------------------------
STATE="$WORK_SESSIONS_REPO/SESSIONS_STATE.md"
[[ -f "$STATE" ]] || die "SESSIONS_STATE.md not found at: $STATE"
ROW="| $SESSION_ID | $GOAL | $TMUX_NAME | sessions/$SESSION_ID | $TODAY | $TODAY | active |"

if grep -q '^| _none yet_' "$STATE"; then
  sed "s#| _none yet_ | | | | | | |#$(sed_repl "$ROW")#" "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
else
  # Insert the new row right after the header separator line (the first
  # `|---|...` line in the file).
  awk -v row="$ROW" '{ print } /^\|---/ && !inserted { print row; inserted=1 }' \
    "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
fi

err ">> registered $SESSION_ID in $STATE"

# --- upsert the portfolio work/wip.json entry ---------------------------
# The session-start ↔ portfolio-wip linkage: a started session must have a
# matching `in progress` item in the work tracker. If the id already exists
# in work/backlog.json, move it to wip (preserving its groomed fields);
# otherwise seed a fresh wip entry from the session's goal/ticket/scope/
# task-type. Idempotent — never duplicates an existing id, never clobbers
# other entries. Skipped only if the work/ tracker isn't present at all.
WIP_JSON="$WORK_SESSIONS_REPO/work/wip.json"
BACKLOG_JSON="$WORK_SESSIONS_REPO/work/backlog.json"
if [[ -f "$WIP_JSON" ]]; then
  SID_ENV="$SESSION_ID" GOAL_ENV="$GOAL" TICKET_ENV="$TICKET" \
  SCOPE_ENV="$SCOPE" TASK_TYPE_ENV="$TASK_TYPE" BLOCKERS_ENV="$BLOCKERS" \
  NOW_ENV="$NOW" WIP_JSON_ENV="$WIP_JSON" BACKLOG_JSON_ENV="$BACKLOG_JSON" \
  python3 "$SCRIPT_DIR/lib/upsert_wip.py" || die "failed to upsert wip.json entry for $SESSION_ID"
  err ">> registered $SESSION_ID in $WIP_JSON (status: in progress)"
else
  err ">> note: no work/wip.json in $WORK_SESSIONS_REPO — skipped wip registration"
fi

# --- always create the agentic-sdlc tool worktree -----------------------
AGENTIC_WT="$SESSION_DIR/worktrees/agentic-sdlc"
err ">> creating detached agentic-sdlc worktree (always included, kept in sync on resume)"
"$SCRIPT_DIR/create-worktree.sh" "$AGENTIC_SDLC_REPO" --dest "$AGENTIC_WT" --detach

# --- link a tmux session (guarded; no-op if tmux is absent) --------------
"$SCRIPT_DIR/session-tmux.sh" ensure "$SESSION_ID" "$SESSION_DIR"

cat >&2 <<EOF

session initialized
  session folder:      $SESSION_DIR
  agentic-sdlc tools:  $AGENTIC_WT
  tmux session:        $TMUX_NAME   (attach:  tmux attach -t $TMUX_NAME)

  cd "$SESSION_DIR"
EOF
