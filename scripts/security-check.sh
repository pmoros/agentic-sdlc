#!/usr/bin/env bash
#
# security-check.sh — run the basic secret-scan + lint checks this repo
# expects to be clean before every push. Same checks CI runs
# (.github/workflows/ci.yml), so a local run before pushing should never
# surprise you.
#
# Requires the tools pinned in .mise.toml — run `mise install` first (or let
# CI do it via the mise GitHub Action).
#
# Usage:
#   scripts/security-check.sh          # run every check
#   scripts/security-check.sh secrets  # run just one check (secrets|shell|actions)
#
# TARGET_DIR (env, default: this repo's root) — lets tests point every check
# at a throwaway fixture repo instead of the real one. Deliberately does NOT
# `cd` there: mise resolves pinned tool versions from .mise.toml by walking
# up from the current directory, so this script stays running from the repo
# root and passes TARGET_DIR as an explicit path to each tool instead.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${TARGET_DIR:-$REPO_ROOT}"
# Always run from the repo root regardless of the caller's cwd — mise
# resolves pinned tool versions by walking up from $PWD, so a caller sitting
# in some other directory (e.g. a test fixture) must not affect resolution.
cd "$REPO_ROOT"

status=0
run_check() {
  local name="$1"
  shift
  echo "── $name ──────────────────────────────────────────────"
  if "$@"; then
    echo "✓ $name passed"
  else
    echo "✗ $name FAILED"
    status=1
  fi
  echo
}

check_secrets() {
  gitleaks detect --source "$TARGET_DIR" --redact -v
}

check_shell() {
  local files=()
  while IFS= read -r -d '' f; do files+=("$f"); done \
    < <(find "$TARGET_DIR/scripts" -name '*.sh' -print0 2>/dev/null)
  [[ ${#files[@]} -eq 0 ]] && return 0
  # -S warning: fail on real bugs, not style/info notes. This codebase uses a
  # deliberately dense style (compact one-liners, aligned case arms) that the
  # info-level style suggestions below this threshold would otherwise fight.
  # (Comment deliberately does not start with the literal word "shellcheck" —
  # ShellCheck parses a leading "# shellcheck ..." comment as a directive.)
  shellcheck -S warning "${files[@]}"
}

check_actions() {
  local files=()
  while IFS= read -r -d '' f; do files+=("$f"); done \
    < <(find "$TARGET_DIR/.github/workflows" \( -name '*.yml' -o -name '*.yaml' \) -print0 2>/dev/null)
  [[ ${#files[@]} -eq 0 ]] && return 0
  actionlint "${files[@]}"
}

target="${1:-all}"
case "$target" in
  secrets) run_check "gitleaks secret scan" check_secrets ;;
  shell) run_check "shellcheck" check_shell ;;
  actions) run_check "actionlint" check_actions ;;
  all)
    run_check "gitleaks secret scan" check_secrets
    run_check "shellcheck" check_shell
    run_check "actionlint" check_actions
    ;;
  *)
    echo "usage: $0 [secrets|shell|actions|all]" >&2
    exit 2
    ;;
esac

exit "$status"
