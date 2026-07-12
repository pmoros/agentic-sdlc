# Fast, isolated repo worktrees — `create-worktree`

A guide to `scripts/create-worktree.sh`, the script behind the
`create_work_tree` command: how to spin up an isolated git worktree of any
repo under `repos/` — including a detached, always-up-to-date
worktree of this repo itself for tool access inside a session — without ever
touching the reference checkout directly (see the Reference Repo Policy in
`AGENTS.md`).

For the `code` monorepo specifically, the script also handles the ~4-minutes-
instead-of-~15 dependency setup below, by skipping the post-checkout install
hook and giving each worktree a copy-on-write `node_modules`.

## The problem

The `code` monorepo uses **Yarn 1 (classic)** with an **~8 GB `node_modules`
(~2,600 top-level packages, ~1M files)**. Yarn classic has no content-addressable
store and no hardlinking, so a cold `yarn install` *resolves and physically
extracts* the whole tree — **~12 min and ~8 GB of disk** per worktree, and it
compounds: a dozen worktrees is ~100 GB and a lot of waiting.

We want each worktree to have its **own** `node_modules` (so installs in one
worktree never corrupt another), but without paying the full install cost every
time.

## Why `git worktree add` itself is slow (the post-checkout hook)

There's a second, less obvious cost. The `code` repo installs a husky
`post-checkout` hook (`core.hooksPath = .husky`) whose last line is:

```sh
NX_DAEMON=false yarn --frozen-lockfile
```

That hook fires on **every checkout — including `git worktree add`** — so a
plain `git worktree add` silently kicks off a full Yarn install (plus nx
postinstall work). That install, not the file materialization, is what makes
worktree creation take minutes.

The hook is skippable: it exits early when `CWI_SKIP_POSTCHECKOUT_HOOK=1` or
`HUSKY=0`. `create-worktree.sh` runs `git worktree add` with both set, so
creation does **not** trigger the hook's install — the worktree's
`node_modules` is set up by the chosen strategy below instead (a no-op for
repos without such a hook). That avoids doing the install twice and is what
makes creation fast.

> If you create worktrees by hand, do the same:
> `CWI_SKIP_POSTCHECKOUT_HOOK=1 git worktree add <path> <branch>`, then set up
> `node_modules` yourself.

## Two mechanisms, don't conflate them

| What | Who handles it | How it's shared |
|------|----------------|-----------------|
| **Tracked source files** | git, natively | One shared `.git` object DB (history not duplicated); each worktree gets its **own real working-copy checkout** of its branch. Not copy-on-write, not copied from main's working dir. |
| **`node_modules`** (gitignored) | this script | Git ignores it, so `worktree add` never creates it. We give each worktree its own copy via **copy-on-write** when the filesystem supports it. |

Other gitignored artifacts (`.nx` cache, `dist/`, `build/`) regenerate on demand
and aren't worth cloning — only `node_modules` is big and expensive enough.

## Dependency strategies

`--deps <mode>` controls this; default is `auto` (clone if the source repo has
`node_modules`, else nothing — most repos under `repos/` aren't
Node projects, so this is a no-op for them).

| `--deps` value | Mechanism | Speed¹ | Real disk | Isolated? | Use when |
|------|-----------|--------|-----------|-----------|----------|
| `auto` *(default)* | CoW clone if `node_modules` exists, else nothing | ~27s or ~0s | ~2 GB or 0 | **yes** (when applicable) | almost always |
| `clone` | CoW clone (APFS `clonefile()` / reflink `cp --reflink`) | ~27s | ~2 GB | **yes** | force CoW even if `auto` would skip it |
| `install` | `yarn install --prefer-offline` | ~12 min | +8 GB | yes | non-CoW FS (e.g. WSL ext4), main has no deps, or you want a guaranteed-clean tree |
| `link` | symlink → main's `node_modules` | ~0.03s | 0 | **no** | dep-stable, code-only branches |
| `none` | nothing | ~0s | 0 | n/a | you'll manage deps yourself |

¹ Measured on the `code` monorepo (macOS/APFS, 8 GB / ~1M-file `node_modules`);
see [Benchmarks](#benchmarks). These are the **node_modules** cost only; every
mode also pays the one-time `git worktree add` (~3.5 min, see above).

**Copy-on-write** creates a *real, independent* `node_modules` that shares disk
blocks with main until something is written — so it costs only ~2 GB of real
disk and is fully isolated. It is **not** instant (the ~1M files take ~27s to
clone even though no data is copied), but it's ~25× faster than a fresh install
or a full copy, which is why it's the default for Node repos. Only `--deps
link` (a symlink) is truly instant — at the cost of isolation.

> **Implementation note:** on macOS the script calls the `clonefile()` syscall
> directly (via `python3`) to clone the whole tree in one shot (~27s). Plain
> `cp -cR` also uses copy-on-write but walks file-by-file and takes ~7.5 min for
> this tree, so it's only the fallback when `python3` is unavailable.

## Decision guide

```
Need a worktree?
│
├─ Not a Node repo (no node_modules)?
│     └─ --deps auto (default) skips dependency setup entirely. Done.
│
├─ Node repo, macOS (APFS) or Linux on btrfs/XFS?
│     └─ use the default (--deps auto -> clone) — fast AND isolated. Done.
│
├─ Node repo, WSL / Linux on ext4 (no reflink)?
│     ├─ branch is code-only (won't touch package.json)?  → --deps link  (instant, shared)
│     └─ branch will change dependencies?                  → --deps install (isolated, slow)
│
└─ Already on a --deps link worktree and now need to add a package?
      └─ --promote <worktree>  (see below) — never `yarn install` through the symlink!
```

## Scenarios: will you change dependencies?

The right strategy depends on two things: **will this branch change dependencies**
(touch `package.json` / `yarn.lock`) and **does the filesystem support
copy-on-write** (macOS/APFS and Linux btrfs/XFS = yes; WSL ext4 / `/mnt/c` = no).
This section only applies to Node repos — everything else just skips deps setup.

| | **Won't change deps** (code-only) | **Will change deps** (add/bump/remove) |
|---|---|---|
| **CoW available** (macOS, btrfs/XFS) | **default** — isolated + ~27s (`--deps link` is faster but buys nothing here) | **default** — isolated; `yarn add` later reconciles only the delta |
| **No CoW** (WSL ext4) | **`--deps link`** — instant, 0 disk; sharing is safe *because you never install* | **`--deps install`** — own tree up front (~12 min once) so installs are safe |

Recovery case (started code-only, now need a package): **`--promote`** (below).

### The key simplification

**On a CoW filesystem you barely need to choose.** The default clone is *both*
fast *and* isolated, so it's the right answer whether or not you change deps —
and you never need `--promote`. The `--deps link` / `--promote` machinery only
earns its keep on **non-CoW filesystems (WSL/ext4)**, where there's a real
tradeoff:

- `--deps link` — instant but shared → safe only if you never install.
- `--deps install` — isolated but ~12 min upfront → needed if you will install.
- `--promote` — the bridge when a `--deps link` worktree unexpectedly needs to install.

### What `--promote` does and why

`--promote` converts a **shared** (`--deps link`) worktree into an **isolated**
one, in place, without losing your work:

```
Before:  worktree/node_modules ──symlink──▶ code/node_modules   (shared with main)

promote: 1. rm the symlink             (link only; main's real dir untouched)
         2. seed an isolated real dir  (CoW-clone main where possible, else clean install)
         3. yarn install --prefer-offline   (reconcile package.json / lock changes)

After:   worktree/node_modules = its OWN real directory   (safe to yarn add / install)
```

It exists to protect one rule: **never run `yarn install` while `node_modules`
is a symlink** — that writes *through* the link into main's tree and corrupts
main plus every sibling worktree. The use case: you created a branch as `--deps
link` thinking it was code-only, then discover you need a dependency. Rather
than tearing it down and recreating with `--deps install` (losing uncommitted
work), `--promote` swaps in an isolated `node_modules` so you can install
safely.

## Changing dependencies in a worktree

- **CoW or `--deps install` worktree** (already isolated): just edit
  `package.json` and run `yarn install --prefer-offline` in the worktree. On a
  CoW worktree the lockfile starts identical to main, so only the changed
  packages are rewritten.

- **`--deps link` worktree**: you must **NOT** run `yarn install` — it writes
  *through* the symlink into main's `node_modules`, corrupting main and every
  other linked worktree. **Promote it first:**

  ```bash
  scripts/create-worktree.sh --promote <work-sessions-repo>/sessions/<session>/worktrees/code-<branch>
  ```

  Promotion breaks the symlink, gives the worktree its own isolated
  `node_modules` (CoW-seeded from main where possible, otherwise a clean
  install), then runs `yarn install --prefer-offline` to reconcile. After that
  the worktree owns its deps and is safe to install into. It's also safe to run
  on an already-isolated worktree (it just reconciles).

## Platform notes

- **macOS**: APFS supports `clonefile()`, which the script calls directly to
  clone `node_modules` in ~27s (one syscall for the whole tree). This is the
  primary, fully-tested path.
- **Linux on btrfs or XFS**: reflink works (`cp --reflink`), so the default CoW
  path is fast and isolated.
- **WSL2 (default ext4) / `/mnt/c` / 9p**: **no reflink**, so CoW is unavailable.
  The script detects this and refuses the clone rather than silently doing a slow
  full copy — use `--deps link` (code-only) or `--deps install` (dep changes).
  For best results keep the repo inside the Linux filesystem, not under `/mnt/c`.

## Detached worktrees and the Reference Repo Policy

Every repo under `repos/` (this one included) is a **read-only
source of truth**: always checked out on its default branch, always kept in
sync with `origin`, and never edited directly — all real work happens in a
worktree. `--sync` (on by default) enforces this by fetching and hard-syncing
the source repo to `origin/<base>` before creating anything, and refuses to
proceed if the source repo has local changes rather than discarding them.

The one repo every session needs read access to but never edits is
`agentic-sdlc` itself (for its scripts/runbooks/`.agents`
tooling). `initialize_work_session_folder` creates a **detached** worktree of
it automatically:

```bash
scripts/create-worktree.sh <agentic-sdlc-repo> --dest <session>/worktrees/agentic-sdlc --detach
```

`--detach` checks out `origin/<default>` with a detached HEAD instead of a
local branch — necessary because the source repo's own checkout already holds
the default branch, and git refuses to check out the same branch live in two
worktrees at once. A detached HEAD doesn't hold that lock. `resume_work_session`
keeps it current with:

```bash
scripts/create-worktree.sh --refresh <session>/worktrees/agentic-sdlc
```

which re-syncs the source repo and fast-forwards the worktree's detached HEAD
to match — no dependency setup is touched. If a session's actual work is
*changing* agentic-sdlc's own code, that's a normal `--branch` worktree
instead (agentic-sdlc treated as a target repo), not this detached one.

## Benchmarks

Measured on macOS/APFS, `node_modules` = 8.0 GB / 2,587 top-level entries /
~1M files, reusing one worktree so the `git worktree add` cost is isolated.

**node_modules step (the strategy you pick):**

| Strategy | Time | Real disk added | Isolated | Notes |
|----------|------|-----------------|----------|-------|
| symlink (`--deps link`) | **0.03s** | 0 | no | one inode; shared with main |
| CoW clone — `clonefile()` *(`--deps auto`/`clone`)* | **27.5s** | ~2 GB | yes | one syscall clones the whole tree |
| CoW clone — `cp -cR` *(fallback)* | 454s (7.5 min) | ~2 GB | yes | per-file clonefile; only if no `python3` |
| fresh install (`--deps install`) | 702s (11.7 min) | +8 GB | yes | re-resolves + runs husky/postinstall |
| full copy (`cp -R`) | 722s (12 min) | +8 GB | yes | naive byte copy, no sharing |
| `--promote` (link → CoW seed → reconcile) | 430s (7 min) | ~2 GB | yes | dominated by the reconcile install |

**Creation step (paid once per worktree, same for every strategy):**

| `git worktree add` | Time |
|--------------------|------|
| with the post-checkout hook (plain `git worktree add`) | + ~12 min (the hook runs a full install) |
| **hook skipped** (what this script does) | **~3.5 min** (source checkout only) |

**End-to-end creation, isolated and ready:**

- **This script (hook skipped + `clonefile` CoW):** ~3.5 min + 27s ≈ **~4 min**, ~2 GB disk.
- **Plain `git worktree add` (old way):** ~3.5 min + ~12 min install ≈ **~15 min**, +8 GB disk.
- **`--deps link`:** ~3.5 min + 0.03s ≈ **~3.5 min**, 0 disk — but shared, not isolated.

**Takeaways:**

1. The biggest win is **skipping the post-checkout hook** (~12 min saved) — most
   of the old "worktree is slow" pain was that hook silently running a full install.
2. CoW is **not instant** (1M files ⇒ ~27s even with one `clonefile()` syscall),
   but it buys full isolation for ~2 GB and ~27s instead of ~12 min and +8 GB.
3. Use the `clonefile()` syscall, **not** `cp -cR` — same disk, 16× faster.
4. `du` reports a CoW clone as the full 8 GB because it counts shared blocks; the
   *true* added disk (from `df`) is ~2 GB.

## Cleanup

```bash
git -C <source-repo> worktree remove --force <worktree-path>
git -C <source-repo> worktree prune
git -C <source-repo> branch -D <branch>     # only if the branch is no longer needed
rm -rf <work-sessions-repo>/sessions/<session>   # if the whole session is done
```

`stop_work_session`/`end_work_session` do this for target-repo worktrees
automatically; the session's `worktrees/agentic-sdlc` worktree is left in
place until the whole session folder is removed.
