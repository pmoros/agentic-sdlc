#!/usr/bin/env bash
#
# aws-login.sh — (re)authenticate AWS SSO profiles for a work session.
#
# Reads the session's .env (AWS_PROFILE / AWS_DEFAULT_REGION /
# AWS_ALLOWED_PROFILES), checks whether the target profile's credentials are
# still valid via `aws sts get-caller-identity`, and only runs `aws sso login`
# when they're missing or expired. Refuses any profile not in the session's
# AWS_ALLOWED_PROFILES allow-list.
#
# Assumes you're already signed in to the SSO start URL in your browser —
# `aws sso login` will open/complete there automatically.
#
# USAGE
#   aws-login.sh [<profile>] [options]
#
# OPTIONS
#   --all                Authenticate every profile in AWS_ALLOWED_PROFILES.
#   --region <region>    Override AWS_DEFAULT_REGION for the identity check.
#   --env-file <path>    .env to load. Default: ./.env, then walk up to 4
#                        parent dirs looking for one.
#   --force              Run `aws sso login` even if credentials are valid.
#   --list               Print the resolved profile, region, and allow-list,
#                        then exit without authenticating.
#   -h, --help           Show this help.
#
# RESOLUTION ORDER for the target profile:
#   1. <profile> positional arg
#   2. AWS_PROFILE from the loaded .env / environment
#   3. cw-test (hard default)
#
# EXAMPLES
#   scripts/aws-login.sh                 # reauth the session default profile
#   scripts/aws-login.sh cw-partner      # reauth a specific allowed profile
#   scripts/aws-login.sh --all           # reauth every allowed profile
#   scripts/aws-login.sh --force         # force a fresh sso login

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }

needval() { [[ -n "${2:-}" && "${2#-}" == "$2" ]] || die "option '$1' requires a value"; }

DEFAULT_PROFILE="cw-test"

PROFILE_ARG=""
REGION_OVERRIDE=""
ENV_FILE=""
DO_ALL=false
FORCE=false
LIST_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)     usage; exit 0 ;;
    --all)         DO_ALL=true; shift ;;
    --force)       FORCE=true; shift ;;
    --list)        LIST_ONLY=true; shift ;;
    --region)      needval "$@"; REGION_OVERRIDE="$2"; shift 2 ;;
    --env-file)    needval "$@"; ENV_FILE="$2"; shift 2 ;;
    -*)            die "unknown option: $1 (try --help)" ;;
    *)             [[ -z "$PROFILE_ARG" ]] && PROFILE_ARG="$1" || die "unexpected arg: $1"; shift ;;
  esac
done

command -v aws >/dev/null 2>&1 || die "aws CLI not found on PATH"

# --- locate and load the session .env ----------------------------------
find_env_file() {
  local dir="$PWD" i
  for ((i = 0; i < 5; i++)); do
    [[ -f "$dir/.env" ]] && { printf '%s\n' "$dir/.env"; return 0; }
    [[ "$dir" == "/" ]] && break
    dir="$(dirname "$dir")"
  done
  return 1
}

if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="$(find_env_file || true)"
fi

if [[ -n "$ENV_FILE" ]]; then
  [[ -f "$ENV_FILE" ]] || die "env file not found: $ENV_FILE"
  err ">> loading env from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  err ">> no .env found — using environment + defaults"
fi

# --- resolve profile, region, allow-list -------------------------------
PROFILE="${PROFILE_ARG:-${AWS_PROFILE:-$DEFAULT_PROFILE}}"
REGION="${REGION_OVERRIDE:-${AWS_DEFAULT_REGION:-us-east-1}}"
ALLOWED="${AWS_ALLOWED_PROFILES:-}"

# is_allowed <profile> — true if allow-list is empty (unrestricted) or contains it
is_allowed() {
  local want="$1" p
  [[ -z "$ALLOWED" ]] && return 0
  IFS=',' read -ra _list <<< "$ALLOWED"
  for p in "${_list[@]}"; do
    p="${p// /}"
    [[ "$p" == "$want" ]] && return 0
  done
  return 1
}

if [[ "$LIST_ONLY" == true ]]; then
  cat >&2 <<EOF
resolved session AWS context:
  profile:          $PROFILE
  region:           $REGION
  allowed profiles: ${ALLOWED:-<unrestricted>}
EOF
  exit 0
fi

# --- reauth one profile ------------------------------------------------
reauth_one() {
  local prof="$1"

  if ! is_allowed "$prof"; then
    die "profile '$prof' is not in AWS_ALLOWED_PROFILES (${ALLOWED:-<unset>}). Add it to the session .env to allow it."
  fi

  if [[ "$FORCE" != true ]] && aws sts get-caller-identity \
        --profile "$prof" --region "$REGION" >/dev/null 2>&1; then
    local acct
    acct="$(aws sts get-caller-identity --profile "$prof" --region "$REGION" \
              --query Account --output text 2>/dev/null || echo '?')"
    err ">> $prof: credentials valid (account $acct) — skipping login"
    return 0
  fi

  err ">> $prof: credentials missing/expired — running 'aws sso login'"
  # Route the device-approval to a browser you're already signed in to the SSO
  # portal on (AWS_SSO_BROWSER in .env), so the approval is a single auto-click.
  # One login mints a token shared by every profile on the same start URL.
  if [[ -n "${AWS_SSO_BROWSER:-}" ]]; then
    BROWSER="$AWS_SSO_BROWSER" aws sso login --profile "$prof" || die "sso login failed for '$prof'"
  else
    aws sso login --profile "$prof" || die "sso login failed for '$prof'"
  fi

  # confirm it worked
  local ident
  if ident="$(aws sts get-caller-identity --profile "$prof" --region "$REGION" \
                --query 'join(`  `, [Account, Arn])' --output text 2>/dev/null)"; then
    err ">> $prof: authenticated — $ident"
  else
    die "sso login ran but get-caller-identity still fails for '$prof'"
  fi
}

if [[ "$DO_ALL" == true ]]; then
  [[ -n "$ALLOWED" ]] || die "--all needs AWS_ALLOWED_PROFILES set in the session .env"
  IFS=',' read -ra _all <<< "$ALLOWED"
  for prof in "${_all[@]}"; do
    prof="${prof// /}"
    [[ -n "$prof" ]] && reauth_one "$prof"
  done
else
  reauth_one "$PROFILE"
fi

err ">> done."
