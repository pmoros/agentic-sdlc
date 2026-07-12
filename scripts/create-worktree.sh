#!/usr/bin/env bash
#
# create-worktree.sh — create a fast, dependency-ready git worktree of ANY
# repo under repos/, for use inside a work-sessions
# session's worktrees/ folder.
#
# WHY THIS EXISTS
#   Repos under repos/ are read-only sources of truth: always
#   checked out on their default branch (or the --base ref given), always
#   kept in sync with origin, and NEVER edited directly. All real work
#   happens in a worktree created by this script under a session's
#   worktrees/ directory — never in the reference checkout itself.
#
#   Some repos (e.g. the `code` monorepo) additionally carry a huge Yarn 1
#   node_modules (~8 GB, ~2,600 packages) whose post-checkout hook runs a
#   full `yarn --frozen-lockfile` on every checkout — that hook firing on
#   `git worktree add` is what makes worktree creation slow (minutes). This
#   script skips it (honors CWI_SKIP_POSTCHECKOUT_HOOK=1 / HUSKY=0) and sets
#   up node_modules itself via copy-on-write, so creation stays fast
#   (~4 min instead of ~15) and each worktree's node_modules is isolated.
#
# MODES
#   create (branch)    create-worktree.sh <repo-path> --dest <path> --branch <name> [options]
#   create (detached)  create-worktree.sh <repo-path> --dest <path> --detach [options]
#   refresh            create-worktree.sh --refresh <worktree-path>
#   promote            create-worktree.sh --promote <worktree-path>
#
# CREATE OPTIONS
#   --base <ref>          Base ref to branch from (or detach at). Default:
#                         <repo-path>'s auto-detected default branch
#                         (origin/HEAD). Override for repos whose working
#                         convention branches off something else (e.g. the
#                         `code` monorepo uses `develop`).
#   --deps <mode>          clone | install | link | none | auto (default: auto)
#                         auto = clone if <repo-path>/node_modules exists,
#                         else none. See docs/create-worktree.md for the
#                         full decision matrix and copy-on-write benchmarks.
#   --sync / --no-sync    Sync <repo-path> to origin/<base> before creating
#                         (default: --sync). This is what keeps the source
#                         checkout a trustworthy, up-to-date reference —
#                         never skip it outside of scripting/testing. Fails
#                         loudly if <repo-path> has local changes, rather
#                         than discarding them, since reference checkouts
#                         should never carry uncommitted work.
#   -h, --help            Show this help.
#
# REFRESH
#   create-worktree.sh --refresh <worktree-path>
#   Re-syncs a DETACHED worktree's source repo to its default branch, then
#   fast-forwards the worktree's detached HEAD to match. Used to keep a
#   session's worktrees/agentic-sdlc worktree current on every resume.
#   Does not touch node_modules.
#
# PROMOTE
#   create-worktree.sh --promote <worktree-path>
#   Isolate a --deps link (symlinked node_modules) worktree, then reconcile
#   with `yarn install --prefer-offline`. Safe to run on an already-isolated
#   worktree too (it just reconciles). See docs/create-worktree.md.
#
# EXAMPLES
#   scripts/create-worktree.sh ../agentic-sdlc \
#     --dest ../work-sessions/sessions/PROJ-1234-fix-thing/worktrees/agentic-sdlc \
#     --detach
#   scripts/create-worktree.sh ../code \
#     --dest ../work-sessions/sessions/PROJ-1234-fix-thing/worktrees/code-proj-1234-fix-thing \
#     --branch feat/PROJ-1234-fix-thing --base develop
#   scripts/create-worktree.sh --refresh .../worktrees/agentic-sdlc
#   scripts/create-worktree.sh --promote .../worktrees/code-proj-1234-fix-thing
#
# See docs/create-worktree.md for the full guide, decision matrix, and
# copy-on-write benchmarks.

set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "error: $*"; exit 1; }

usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; /^set -euo/d'; }

OS="$(uname -s)"

# clone_tree <src-dir> <dst-dir> — make an ISOLATED copy of a directory using
# copy-on-write. dst must NOT already exist.
#
#   macOS: a single clonefile() syscall clones the whole tree in one shot
#     (~27s for a 1M-file node_modules, ~2 GB real disk). `cp -cR` also uses
#     clonefile but walks file-by-file (~7.5 min for the same tree), so we call
#     the syscall directly via python3 and only fall back to `cp -cR` if python3
#     is missing.
#   Linux: reflink (`cp -a --reflink=always`) on btrfs/XFS; fails on ext4.
clone_tree() {
  local src="$1" dst="$2"
  case "$OS" in
    Darwin)
      if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import ctypes,sys
libc=ctypes.CDLL("/usr/lib/libSystem.dylib",use_errno=True)
cf=libc.clonefile; cf.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint32]; cf.restype=ctypes.c_int
rc=cf(sys.argv[1].encode(),sys.argv[2].encode(),0)
sys.exit(0 if rc==0 else (ctypes.get_errno() or 1))' "$src" "$dst"
      else
        cp -cR "$src" "$dst"
      fi
      ;;
    Linux)  cp -a --reflink=always "$src" "$dst" ;;     # btrfs/XFS reflink (-a: recurse)
    *)      return 2 ;;
  esac
}

clone_unsupported_hint() {
  case "$OS" in
    Darwin) echo "clonefile (cp -c) failed — is this volume APFS? Use --deps install (isolated) or --deps link (shared)." ;;
    Linux)  echo "reflink unavailable on this filesystem (ext4/9p have none; need btrfs or XFS). Use --deps link (instant, shared) or --deps install (isolated). On WSL keep the repo inside the Linux FS, not /mnt/c." ;;
    *)      echo "copy-on-write not supported on $OS. Use --deps install or --deps link." ;;
  esac
}

# needval <flag> <next-token...> — assert a value-taking option got a value
# (not missing, empty, or another flag).
needval() { [[ -n "${2:-}" && "${2#-}" == "$2" ]] || die "option '$1' requires a value"; }

# default_branch <repo-path> — the repo's default branch name (origin/HEAD).
default_branch() {
  local repo="$1" ref
  ref="$(git -C "$repo" symbolic-ref -q refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ -n "$ref" ]]; then
    printf '%s\n' "${ref#refs/remotes/origin/}"
    return
  fi
  ref="$(git -C "$repo" remote show origin 2>/dev/null | sed -n 's/^ *HEAD branch: //p')"
  [[ -n "$ref" ]] || die "could not auto-detect default branch for $repo — pass --base explicitly"
  printf '%s\n' "$ref"
}

# sync_repo <repo-path> <base-ref> — fetch + hard-sync <repo-path>'s checkout
# to origin/<base-ref>. Enforces the read-only-reference-checkout rule: dies
# rather than discarding local changes, since a reference checkout should
# never carry any.
sync_repo() {
  local repo="$1" base="$2"
  [[ -z "$(git -C "$repo" status --porcelain)" ]] \
    || die "$repo has local changes — reference repos under repos/ must stay clean (do work only in a session worktree). Resolve manually, then retry."
  err ">> syncing $repo to origin/$base"
  git -C "$repo" fetch origin >&2
  git -C "$repo" checkout -q -B "$base" "origin/$base"
}

# --- parse args --------------------------------------------------------
REPO_PATH=""
DEST=""
BRANCH=""
DETACH=0
BASE=""
DEPS_MODE="auto"
DO_SYNC=1
REFRESH_WT=""
PROMOTE_WT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)   usage; exit 0 ;;
    --dest)      needval "$@"; DEST="$2"; shift 2 ;;
    --branch)    needval "$@"; BRANCH="$2"; shift 2 ;;
    --detach)    DETACH=1; shift ;;
    --base)      needval "$@"; BASE="$2"; shift 2 ;;
    --deps)      needval "$@"; DEPS_MODE="$2"; shift 2 ;;
    --sync)      DO_SYNC=1; shift ;;
    --no-sync)   DO_SYNC=0; shift ;;
    --refresh)   needval "$@"; REFRESH_WT="$2"; shift 2 ;;
    --promote)   needval "$@"; PROMOTE_WT="$2"; shift 2 ;;
    -*)          die "unknown option: $1 (try --help)" ;;
    *)           [[ -z "$REPO_PATH" ]] && REPO_PATH="$1" || die "unexpected arg: $1"; shift ;;
  esac
done

MODES_SET=0
[[ -n "$REFRESH_WT" ]] && MODES_SET=$((MODES_SET + 1))
[[ -n "$PROMOTE_WT" ]] && MODES_SET=$((MODES_SET + 1))
[[ -n "$REPO_PATH" || -n "$DEST" || -n "$BRANCH" || $DETACH -eq 1 ]] && MODES_SET=$((MODES_SET + 1))
[[ $MODES_SET -le 1 ]] || die "specify only one of: create (<repo-path> --dest ...), --refresh, --promote"

# =====================================================================
# REFRESH MODE — fast-forward a detached worktree to its origin repo's
# current default branch.
# =====================================================================
if [[ -n "$REFRESH_WT" ]]; then
  WT="$(cd "$REFRESH_WT" 2>/dev/null && pwd)" || die "worktree path not found: $REFRESH_WT"
  git -C "$WT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git worktree: $WT"

  MAIN="$(git -C "$WT" worktree list --porcelain | awk '/^worktree /{print $2; exit}')"
  REFRESH_BASE="${BASE:-$(default_branch "$MAIN")}"

  [[ $DO_SYNC -eq 1 ]] && sync_repo "$MAIN" "$REFRESH_BASE"

  err ">> refreshing detached worktree $WT -> origin/$REFRESH_BASE"
  git -C "$WT" fetch origin >&2
  git -C "$WT" checkout -q --detach "origin/$REFRESH_BASE"

  cat >&2 <<EOF

worktree refreshed
  worktree: $WT
  ref:      origin/$REFRESH_BASE ($(git -C "$WT" rev-parse --short HEAD))
EOF
  exit 0
fi

# =====================================================================
# PROMOTE MODE — isolate an existing worktree, then reconcile its deps.
# =====================================================================
if [[ -n "$PROMOTE_WT" ]]; then
  WT="$(cd "$PROMOTE_WT" 2>/dev/null && pwd)" || die "worktree path not found: $PROMOTE_WT"
  git -C "$WT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git worktree: $WT"

  # The main checkout is the first entry in `git worktree list`.
  MAIN="$(git -C "$WT" worktree list --porcelain | awk '/^worktree /{print $2; exit}')"
  MAIN_NM="$MAIN/node_modules"
  NM="$WT/node_modules"

  if [[ -L "$NM" ]]; then
    err ">> $NM is a symlink -> $(readlink "$NM"); breaking it"
    rm "$NM"                                   # unlinks the symlink only; main untouched
    if [[ -d "$MAIN_NM" && ! -L "$MAIN_NM" ]]; then
      clone_tree "$MAIN_NM" "$NM" 2>/dev/null || true   # exit code unreliable; check below
    fi
    if [[ "$(ls -A "$NM" 2>/dev/null | wc -l | tr -d ' ')" -gt 0 ]]; then
      err ">> CoW-seeded isolated node_modules from main; reconciling"
    else
      err ">> no CoW seed available; doing a clean install"
    fi
  elif [[ -d "$NM" ]]; then
    err ">> $NM is already an isolated directory; reconciling only"
  else
    err ">> no node_modules present; installing fresh"
  fi

  err ">> yarn install --prefer-offline in $WT"
  (cd "$WT" && yarn install --prefer-offline)

  cat >&2 <<EOF

promoted — worktree now has its own isolated node_modules
  worktree: $WT
  (safe to add/remove packages and run yarn here; main is unaffected)
EOF
  exit 0
fi

# =====================================================================
# CREATE MODE
# =====================================================================
[[ -n "$REPO_PATH" ]] || { usage; exit 2; }
[[ -d "$REPO_PATH/.git" ]] || die "not a git repo checkout: $REPO_PATH"
REPO_PATH="$(cd "$REPO_PATH" && pwd)"

[[ -n "$DEST" ]] || die "--dest is required"
[[ -n "$BRANCH" || $DETACH -eq 1 ]] || die "specify --branch <name> or --detach"
[[ -z "$BRANCH" || $DETACH -eq 0 ]] || die "--branch and --detach are mutually exclusive"
[[ -e "$DEST" ]] && die "worktree path already exists: $DEST"

BASE="${BASE:-$(default_branch "$REPO_PATH")}"
[[ $DO_SYNC -eq 1 ]] && sync_repo "$REPO_PATH" "$BASE"

mkdir -p "$(dirname "$DEST")"

# The `code` monorepo (and possibly others) has a husky post-checkout hook
# that runs a full `yarn --frozen-lockfile` on every checkout — that is the
# real reason `git worktree add` can be slow (minutes), NOT file
# materialization. We skip it (the hook honors
# CWI_SKIP_POSTCHECKOUT_HOOK=1 / HUSKY=0) and set up node_modules ourselves
# below via the chosen strategy. Skipping avoids doing the install twice and
# is what makes creation fast; it's a no-op for repos without such a hook.
SKIP_HOOK_ENV=(env CWI_SKIP_POSTCHECKOUT_HOOK=1 HUSKY=0)

if [[ $DETACH -eq 1 ]]; then
  err ">> creating detached worktree at origin/$BASE (post-checkout install hook skipped)"
  "${SKIP_HOOK_ENV[@]}" git -C "$REPO_PATH" worktree add --detach "$DEST" "origin/$BASE"
elif git -C "$REPO_PATH" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  # Branch exists — adopt it (must not be checked out in another worktree).
  CHECKED_OUT_AT="$(git -C "$REPO_PATH" worktree list --porcelain \
      | awk -v b="refs/heads/$BRANCH" '/^worktree /{w=$2} $1=="branch" && $2==b {print w; exit}')"
  [[ -z "$CHECKED_OUT_AT" ]] || die "branch '$BRANCH' is already checked out at: $CHECKED_OUT_AT"
  err ">> adopting existing branch '$BRANCH' (post-checkout install hook skipped)"
  "${SKIP_HOOK_ENV[@]}" git -C "$REPO_PATH" worktree add "$DEST" "$BRANCH"
else
  err ">> creating branch '$BRANCH' from origin/$BASE (post-checkout install hook skipped)"
  "${SKIP_HOOK_ENV[@]}" git -C "$REPO_PATH" worktree add -b "$BRANCH" "$DEST" "origin/$BASE"
fi

# --- node_modules ----------------------------------------------------------
MAIN_NM="$REPO_PATH/node_modules"

if [[ "$DEPS_MODE" == "auto" ]]; then
  [[ -e "$MAIN_NM" ]] && DEPS_MODE="clone" || DEPS_MODE="none"
fi

setup_clone() {
  [[ -d "$MAIN_NM" && ! -L "$MAIN_NM" ]] || die "$REPO_PATH/node_modules missing/symlinked — run a real install there first, or use --deps install"
  rm -rf "$DEST/node_modules"
  err ">> CoW-cloning node_modules ..."
  # node_modules holds symlinks (e.g. .bin/*), so cp can exit non-zero on a
  # benign warning even when the tree cloned fine. Judge success by completeness
  # (top-level entry count vs main), not by exit code.
  clone_tree "$MAIN_NM" "$DEST/node_modules" 2>/dev/null || true
  local want have
  want=$(ls -A "$MAIN_NM" 2>/dev/null | wc -l | tr -d ' ')
  have=$(ls -A "$DEST/node_modules" 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$have" -eq 0 ]]; then
    rm -rf "$DEST/node_modules"
    die "CoW clone produced nothing. $(clone_unsupported_hint)"
  elif [[ "$have" -lt "$want" ]]; then
    err "!! CoW clone copied $have/$want top-level entries — incomplete; reconcile with 'yarn install --prefer-offline' or recreate with --deps install"
  fi
  # If the worktree's lockfile diverged from main, the clone is a correct base
  # but stale — tell the user to reconcile it in-place (fast, offline).
  if [[ -f "$REPO_PATH/yarn.lock" ]] && ! cmp -s "$REPO_PATH/yarn.lock" "$DEST/yarn.lock" 2>/dev/null; then
    err "!! yarn.lock differs from main — run: (cd \"$DEST\" && yarn install --prefer-offline)"
  fi
}

setup_install() {
  err ">> yarn install --prefer-offline (isolated, may take minutes) ..."
  (cd "$DEST" && yarn install --prefer-offline)
}

setup_link() {
  [[ -d "$MAIN_NM" && ! -L "$MAIN_NM" ]] || die "$REPO_PATH/node_modules missing/symlinked"
  rm -rf "$DEST/node_modules"
  ln -s "$MAIN_NM" "$DEST/node_modules"
  err "!! linked node_modules -> main (SHARED, not isolated). Do NOT run 'yarn install' here — use '--promote $DEST' first."
}

case "$DEPS_MODE" in
  clone)   setup_clone ;;
  install) setup_install ;;
  link)    setup_link ;;
  none)    err ">> skipping node_modules (--deps none)" ;;
  *)       die "unknown --deps mode: $DEPS_MODE (want clone|install|link|none|auto)" ;;
esac

# --- done ------------------------------------------------------------------
if [[ $DETACH -eq 1 ]]; then
  REF_DESC="detached @ origin/$BASE"
else
  REF_DESC="$BRANCH (from origin/$BASE)"
fi

cat >&2 <<EOF

worktree ready
  repo:     $REPO_PATH
  ref:      $REF_DESC
  deps:     $DEPS_MODE
  path:     $DEST

  cd "$DEST"
EOF
