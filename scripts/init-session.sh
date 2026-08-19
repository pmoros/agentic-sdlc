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
REOPEN_ITEM=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)             usage; exit 0 ;;
    --goal)                needval "$@"; GOAL="$2"; shift 2 ;;
    --ticket)               needval "$@"; TICKET="$2"; shift 2 ;;
    --scope)                needval "$@"; SCOPE="$2"; shift 2 ;;
    --task-type)            needval "$@"; TASK_TYPE="$2"; shift 2 ;;
    --blockers)              needval "$@"; BLOCKERS="$2"; shift 2 ;;
    --reopen-item)            needval "$@"; REOPEN_ITEM="$2"; shift 2 ;;
    --work-sessions-repo)   needval "$@"; WORK_SESSIONS_REPO="$2"; shift 2 ;;
    --agentic-sdlc-repo)    needval "$@"; AGENTIC_SDLC_REPO="$2"; shift 2 ;;
    -*)                     die "unknown option: $1 (try --help)" ;;
    *)                      [[ -z "$SESSION_ID" ]] && SESSION_ID="$1" || die "unexpected arg: $1"; shift ;;
  esac
done

# --reopen-item: the session id (episode N's) can't be known until we've
# read the item's existing sessions[] (below), so a positional arg isn't
# meaningful in this mode — ignore it rather than requiring callers to
# invent a placeholder.
[[ -n "$REOPEN_ITEM" || -n "$SESSION_ID" ]] || { usage; exit 2; }
[[ -n "$GOAL" ]] || die "--goal is required"
[[ -d "$WORK_SESSIONS_REPO/.git" ]] || die "work-sessions repo not found at: $WORK_SESSIONS_REPO (pass --work-sessions-repo)"
[[ -d "$AGENTIC_SDLC_REPO/.git" ]] || die "agentic-sdlc repo not found at: $AGENTIC_SDLC_REPO (pass --agentic-sdlc-repo)"

# --- ADH-011: resolve the episode session id for --reopen-item ---------
# The item file must already exist — reopening a nonexistent item is a
# contradiction, not a fallback-to-create (that's the plain, no-flag path).
# Episode numbering matches define_work_item.py's own max(episode_number)+1
# rule exactly (a structurally-empty sessions[] counts as implicit episode
# 1) so the id computed here is always the one --open-episode will use.
if [[ -n "$REOPEN_ITEM" ]]; then
  REOPEN_ITEM_FILE="$WORK_SESSIONS_REPO/work/items/$REOPEN_ITEM.json"
  [[ -f "$REOPEN_ITEM_FILE" ]] \
    || die "cannot reopen $REOPEN_ITEM: no item file found at $REOPEN_ITEM_FILE (reopening a nonexistent item is not supported — start a normal session instead)"
  NEXT_EPISODE="$(python3 -c "
import json
d = json.load(open('$REOPEN_ITEM_FILE'))
nums = [e.get('episode_number', 1) for e in (d.get('sessions') or [])]
print((max(nums) if nums else 1) + 1)
")"
  SESSION_ID="${REOPEN_ITEM}--e${NEXT_EPISODE}"
  err ">> reopening $REOPEN_ITEM as episode $NEXT_EPISODE ($SESSION_ID)"
fi

TEMPLATE_DIR="$WORK_SESSIONS_REPO/session-template"
[[ -d "$TEMPLATE_DIR" ]] || die "session-template not found at: $TEMPLATE_DIR"

SESSION_DIR="$WORK_SESSIONS_REPO/sessions/$SESSION_ID"
[[ -e "$SESSION_DIR" ]] && die "session folder already exists: $SESSION_DIR"

# --- migration safety guard (fail before any side effect) --------------
# work/items/ becomes the source of truth once migrated (see
# scripts/migrate-items-v2.sh); backlog.json/wip.json become generated
# views. If work/items/ doesn't exist yet AND backlog.json/wip.json still
# hold real (un-migrated) content, refuse now — before creating the
# session folder, registering it in SESSIONS_STATE.md, or touching the
# item store — rather than partway through. Starting a session here would
# derive views from an empty item store while real un-migrated data sits
# unreachable via those views.
ITEMS_DIR="$WORK_SESSIONS_REPO/work/items"
BACKLOG_JSON="$WORK_SESSIONS_REPO/work/backlog.json"
WIP_JSON="$WORK_SESSIONS_REPO/work/wip.json"

# A raw `ls -A` would count a crash-orphaned `<id>.json.lock/` dir (left
# behind if a prior define-work-item.sh run was killed before its EXIT trap
# released it) as "populated" with zero real items — silently defeating
# this guard. Only actual `*.json` files count, matching
# lib/regenerate_views.py's own item-file filtering.
items_dir_populated() {
  [[ -d "$ITEMS_DIR" ]] || return 1
  local f
  for f in "$ITEMS_DIR"/*.json; do
    [[ -f "$f" ]] && return 0
  done
  return 1
}

# Fails CLOSED: a file that exists but doesn't parse as a non-empty JSON
# object is treated as "might hold real content" (exit 0 -> triggers the
# guard), not silently as empty — a corrupt backlog.json/wip.json is
# exactly the kind of thing this guard must not paper over.
json_object_nonempty() {
  [[ -f "$1" ]] || return 1
  python3 -c "
import json, sys
try:
    data = json.load(open('$1'))
except Exception:
    sys.exit(0)
sys.exit(0 if isinstance(data, dict) and data else 1)
" 2>/dev/null
}

if ! items_dir_populated && { json_object_nonempty "$BACKLOG_JSON" || json_object_nonempty "$WIP_JSON"; }; then
  die "work/items/ doesn't exist yet, but backlog.json/wip.json still hold real content — run 'scripts/migrate-items-v2.sh --dry-run' (then --commit) against $WORK_SESSIONS_REPO before starting a new session"
fi

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
# ADH-011: every row now carries an Item column — the underlying item id,
# which equals the Session ID for an ordinary (episode-1) session, and the
# reopened item's id (without the --eN suffix) for an episode row. This
# makes every episode of the same item joinable by that column regardless
# of which row you're looking at.
STATE="$WORK_SESSIONS_REPO/SESSIONS_STATE.md"
[[ -f "$STATE" ]] || die "SESSIONS_STATE.md not found at: $STATE"
ITEM_ID_FOR_ROW="${REOPEN_ITEM:-$SESSION_ID}"
ROW="| $SESSION_ID | $ITEM_ID_FOR_ROW | $GOAL | $TMUX_NAME | sessions/$SESSION_ID | $TODAY | $TODAY | active |"

if grep -q '^| _none yet_' "$STATE"; then
  sed "s#| _none yet_ | | | | | | | |#$(sed_repl "$ROW")#" "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
else
  # Insert the new row right after the header separator line (the first
  # `|---|...` line in the file).
  awk -v row="$ROW" '{ print } /^\|---/ && !inserted { print row; inserted=1 }' \
    "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
fi

err ">> registered $SESSION_ID in $STATE"

# --- register the item in the per-item store (work/items/<id>.json) ----
# The session-start <-> portfolio linkage: a started session must have a
# matching `in progress` item. This calls the ONE canonical constructor,
# define-work-item.sh, and asks it to record the "session started" event
# through its own locked write path (--record-event/--current-state) —
# replacing the old lib/upsert_wip.py, which duplicated this shaping logic
# separately from #triage-inbox and had already diverged from it (ADH-008).
# (The migration safety guard for this step already ran above, before any
# side effect, in case it needed to refuse.)
if [[ -n "$REOPEN_ITEM" ]]; then
  # ADH-011: this is a new episode of an EXISTING item — the item file is
  # keyed by $REOPEN_ITEM, never by $SESSION_ID (which carries the --eN
  # suffix and must never become a second item file). --open-episode
  # appends to sessions[], flips status to "in progress", and records its
  # own "reopened as episode N" history entry — no --record-event needed.
  "$SCRIPT_DIR/define-work-item.sh" "$REOPEN_ITEM" --open-episode "$SESSION_ID" \
    --work-sessions-repo "$WORK_SESSIONS_REPO" \
    || die "failed to reopen $REOPEN_ITEM as episode via $SESSION_ID"
  err ">> reopened $REOPEN_ITEM in $REOPEN_ITEM_FILE (new episode: $SESSION_ID)"
elif [[ -f "$WIP_JSON" || -d "$ITEMS_DIR" ]]; then
  ITEM_FILE="$ITEMS_DIR/$SESSION_ID.json"
  ALREADY_ACTIVE=0
  if [[ -f "$ITEM_FILE" ]]; then
    CUR_STATUS="$(python3 -c "import json; print(json.load(open('$ITEM_FILE')).get('status',''))" 2>/dev/null || echo "")"
    [[ "$CUR_STATUS" == "in progress" ]] && ALREADY_ACTIVE=1
  fi

  if [[ "$ALREADY_ACTIVE" -eq 1 ]]; then
    err ">> $SESSION_ID already in progress in $ITEM_FILE — leaving item untouched (idempotent)"
  else
    DEFINE_ARGS=(--status "in progress" --record-event "session started" --by "init-session.sh")
    if [[ -n "$BLOCKERS" ]]; then
      DEFINE_ARGS+=(--current-state "$BLOCKERS" --blocked)
    else
      DEFINE_ARGS+=(--current-state "$GOAL")
    fi
    if [[ ! -f "$ITEM_FILE" ]]; then
      # Fresh item — seed from the session details (mirrors the old
      # upsert_wip.py "seed fresh" path). An existing/groomed item keeps
      # its own title/description/scope/ticket untouched.
      DEFINE_ARGS+=(--description "$GOAL")
      [[ -n "$SCOPE" ]] && DEFINE_ARGS+=(--scope "$SCOPE")
      [[ -n "$TICKET" ]] && DEFINE_ARGS+=(--ticket "$TICKET")
      [[ -n "$TASK_TYPE" ]] && DEFINE_ARGS+=(--task-type "$TASK_TYPE")
    fi
    "$SCRIPT_DIR/define-work-item.sh" "$SESSION_ID" "${DEFINE_ARGS[@]}" --work-sessions-repo "$WORK_SESSIONS_REPO" \
      || die "failed to register $SESSION_ID in the item store"
    err ">> registered $SESSION_ID in $ITEM_FILE (status: in progress)"
  fi
else
  err ">> note: no work/wip.json or work/items/ in $WORK_SESSIONS_REPO — skipped item registration"
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
