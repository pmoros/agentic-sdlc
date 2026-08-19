#!/usr/bin/env python3
"""Pure migration logic for the one-time item-store migration
(scripts/migrate-items-v2.sh): backlog.json/wip.json (old shared-file
store) -> work/items/<id>.json (one file per item).

See work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md §5.

The decision-making functions below are pure (dicts/strings in, dicts/lists
out) so they can be unit-tested without touching the filesystem:

- :func:`merge_sources` combines backlog.json + wip.json into one item map.
- :func:`parse_sessions_state` reads SESSIONS_STATE.md's registry table.
- :func:`build_session_entry` / :func:`migrate_item` shape one migrated item
  — the entire source item, untouched, plus `id` and a single first-episode
  `sessions[]` entry derived from its registry row (empty list if the item
  was never a session).
- :func:`diff_item` / :func:`verify_item` back --dry-run's per-item diff and
  --commit's byte-identical verification pass, respectively.

`work/scratchpad.json` is explicitly out of scope (SPEC.md Constraints) — it
is read only to report its entry count as an informational, untouched note
in --dry-run output, never migrated into an item.

I/O (reading the source files, writing staged/final item files, the
--commit staging/verify/move sequence, --commit-cleanup's renames) lives in
the ``run_*``/:func:`main` functions below; everything above them is pure.
"""
import json
import os
import shutil
import sys

NEW_FIELDS = ("id", "sessions")
_CLOSED_STATUSES = {"done", "stopped"}


# --------------------------------------------------------------------------
# Pure logic
# --------------------------------------------------------------------------

def merge_sources(backlog, wip):
    """Merge ``backlog`` + ``wip`` item maps into one ``{id: item}``.

    Raises ``ValueError`` if the same id appears in both — each item should
    live in exactly one view; a collision means the source data is already
    inconsistent and migrating it blind would silently pick one arbitrarily.
    """
    collisions = set(backlog) & set(wip)
    if collisions:
        raise ValueError(
            f"item id(s) present in both backlog.json and wip.json: {sorted(collisions)}")
    merged = dict(backlog)
    merged.update(wip)
    return merged


def parse_sessions_state(text):
    """Parse SESSIONS_STATE.md's markdown table into
    ``{session_id: {title, tmux_session, folder, created, last_change, status}}``.

    Skips the header row, the ``|---|...` separator row, and the
    ``_none yet_`` placeholder row a freshly-scaffolded registry ships with.
    Any row that doesn't have exactly 7 cells (the current table shape) is
    skipped rather than raising — a malformed/commented line shouldn't abort
    the whole parse.
    """
    rows = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 7:
            continue
        session_id = cells[0]
        if not session_id or session_id == "Session ID" or session_id == "_none yet_":
            continue
        if set(session_id) <= {"-"}:
            continue
        rows[session_id] = {
            "title": cells[1],
            "tmux_session": cells[2],
            "folder": cells[3],
            "created": cells[4],
            "last_change": cells[5],
            "status": cells[6],
        }
    return rows


def build_session_entry(item_id, row):
    """Return the single first-episode ``sessions[]`` entry for ``item_id``,
    derived from its SESSIONS_STATE.md registry ``row``. ``None`` when
    ``row`` is ``None`` (the item was never a session — e.g. a groomed-but-
    never-started backlog item) meaning the migrated item's ``sessions``
    stays an empty list, matching the fresh-item lifecycle default in
    ``define_work_item.py``.
    """
    if row is None:
        return None
    created = row.get("created") or ""
    opened = f"{created}T00:00:00Z" if created else None
    closed = None
    if row.get("status") in _CLOSED_STATUSES and row.get("last_change"):
        closed = f"{row['last_change']}T00:00:00Z"
    return {
        "episode_id": item_id,
        "episode_number": 1,
        "folder": row.get("folder") or f"sessions/{item_id}/",
        "opened": opened,
        "closed": closed,
    }


def migrate_item(item_id, source_item, sessions_row=None):
    """Return the migrated ``work/items/<id>.json`` shape for one item — the
    entire source item, unchanged, plus ``id`` and ``sessions``. Pure — no
    I/O, no mutation of ``source_item``.
    """
    migrated = dict(source_item)
    migrated["id"] = item_id
    entry = build_session_entry(item_id, sessions_row)
    migrated["sessions"] = [entry] if entry else []
    return migrated


def diff_item(item_id, source_item, migrated_item):
    """Describe what --commit would produce for one item, for --dry-run's
    per-item diff output: which fields are new (not present on the source)
    vs. which are carried over unchanged. Pure.
    """
    new_fields = sorted(k for k in migrated_item if k not in source_item)
    unchanged_fields = sorted(k for k in source_item if k in migrated_item)
    return {"new_fields": new_fields, "unchanged_fields": unchanged_fields}


def verify_item(source_item, migrated_item):
    """Return the list of field names present on ``source_item`` whose value
    in ``migrated_item`` differs (or is missing) — empty means every
    pre-existing field survived byte-identical. Pure.
    """
    return [key for key, value in source_item.items() if migrated_item.get(key) != value]


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

def _load_json_file(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path) as fh:
        text = fh.read().strip()
    return json.loads(text) if text else {}


def _dump_json_file(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def load_all_sources(work_dir):
    backlog = _load_json_file(os.path.join(work_dir, "backlog.json"))
    wip = _load_json_file(os.path.join(work_dir, "wip.json"))
    return merge_sources(backlog, wip)


def load_sessions_state(work_sessions_repo):
    if not work_sessions_repo:
        return {}
    path = os.path.join(work_sessions_repo, "SESSIONS_STATE.md")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return parse_sessions_state(fh.read())


def _scratchpad_count(work_dir):
    return len(_load_json_file(os.path.join(work_dir, "scratchpad.json")))


def run_dry_run(work_dir, work_sessions_repo, out=None):
    out = out or sys.stdout
    sources = load_all_sources(work_dir)
    registry = load_sessions_state(work_sessions_repo)

    for item_id in sorted(sources):
        source_item = sources[item_id]
        migrated = migrate_item(item_id, source_item, registry.get(item_id))
        d = diff_item(item_id, source_item, migrated)
        print(
            f"{item_id}: would write work/items/{item_id}.json "
            f"(new fields: {', '.join(d['new_fields']) or 'none'})",
            file=out,
        )

    n_scratchpad = _scratchpad_count(work_dir)
    print(
        f"-- dry-run summary: {len(sources)} item(s) would be migrated; "
        f"writes nothing; {n_scratchpad} scratchpad.json note(s) left "
        "untouched (out of scope) --",
        file=out,
    )
    return 0


def _clean_stale_staging(staging_dir):
    if os.path.isdir(staging_dir):
        shutil.rmtree(staging_dir)


def _precheck_commit(items_dir, staging_dir):
    """Refuse if ``items_dir`` already holds a real prior migration.
    Otherwise clear any stale staging left by an interrupted prior attempt
    so a fresh one can be built. ``staging_dir`` is a SIBLING of
    ``items_dir`` (not nested inside it) — see :func:`run_commit` for why
    that layout matters.
    """
    if os.path.isdir(items_dir) and os.listdir(items_dir):
        raise RuntimeError(
            "work/items/ already exists and contains items — migration "
            "is a one-time step; refusing to run again")
    _clean_stale_staging(staging_dir)


def run_commit(work_dir, work_sessions_repo, out=None, _fault_inject_id=None,
               _fault_fail_final_move=False):
    """``_fault_inject_id``, if given, deliberately corrupts that item's
    staged write before the verification re-read — a test-only hook (there
    is no legitimate code path that produces a verification mismatch; this
    simulates one, e.g. a corrupted/interrupted write) exercising the
    single-failing-item-aborts-the-whole-commit contract end-to-end. See
    MIGRATE_FAULT_CORRUPT_ID_ENV below.

    ``_fault_fail_final_move``, if true, simulates the final atomic move
    itself failing (e.g. disk full, permission error) — a second, distinct
    test-only hook, since a REAL atomic-rename failure can't be reliably
    triggered from a black-box test. See MIGRATE_FAULT_FAIL_FINAL_MOVE_ENV.
    """
    out = out or sys.stdout
    items_dir = os.path.join(work_dir, "items")
    # A SIBLING of items_dir, not nested inside it — deliberately, so the
    # final step below can be a single `os.replace(staging_dir, items_dir)`.
    # A directory cannot be atomically renamed into its own parent, so an
    # earlier version of this function nested staging inside items_dir and
    # had to fall back to a per-file move loop — NOT atomic as a whole, and
    # a crash mid-loop could leave work/items/ with a real subset of items
    # present, which is exactly the "partial migration state" this design
    # promises never happens (ADH-008 Gate B QA finding, see
    # docs/gate-a-review-r1.md-style record — the review that caught this).
    staging_dir = os.path.join(work_dir, ".items-migration-staging")

    _precheck_commit(items_dir, staging_dir)

    sources = load_all_sources(work_dir)
    registry = load_sessions_state(work_sessions_repo)

    os.makedirs(staging_dir, exist_ok=True)

    try:
        migrated_by_id = {}
        for item_id, source_item in sources.items():
            migrated = migrate_item(item_id, source_item, registry.get(item_id))
            migrated_by_id[item_id] = migrated
            staged_path = os.path.join(staging_dir, f"{item_id}.json")
            if item_id == _fault_inject_id:
                _dump_json_file(staged_path, {**migrated, "title": "__corrupted-by-fault-injection__"})
            else:
                _dump_json_file(staged_path, migrated)

        # Verification: independently re-read every staged file back and
        # compare against the source — this is the gate for calling the
        # migration safe, not the write above.
        for item_id, source_item in sources.items():
            with open(os.path.join(staging_dir, f"{item_id}.json")) as fh:
                reread = json.load(fh)
            mismatches = verify_item(source_item, reread)
            if mismatches:
                raise RuntimeError(
                    f"verification failed for {item_id}: field(s) "
                    f"{', '.join(mismatches)} do not match the source")

        if _fault_fail_final_move:
            raise OSError("simulated failure during final atomic move (test-only fault injection)")

        # The ENTIRE staged, verified tree becomes work/items/ in ONE
        # syscall — either it's all there or (on any failure above, or a
        # genuine OS-level failure of this call itself) none of it is.
        # There is no window in which work/items/ holds a partial result.
        os.replace(staging_dir, items_dir)
    except Exception:
        # Every failure path — a bad write, a verification mismatch, or the
        # final move itself — lands here. staging_dir is always what's left
        # to clean up; items_dir is untouched until the atomic move above
        # succeeds, so it can never be left holding a partial result.
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    print(f"-- migrated {len(migrated_by_id)} item(s) to work/items/ --", file=out)
    print(
        "-- backlog.json/wip.json left in place, now stale; run "
        "--commit-cleanup after review --",
        file=out,
    )
    return 0


def run_verify(work_dir, out=None):
    out = out or sys.stdout
    items_dir = os.path.join(work_dir, "items")
    sources = load_all_sources(work_dir)

    problems = []
    for item_id, source_item in sources.items():
        item_path = os.path.join(items_dir, f"{item_id}.json")
        if not os.path.exists(item_path):
            problems.append(f"{item_id}: missing from work/items/")
            continue
        with open(item_path) as fh:
            migrated = json.load(fh)
        mismatches = verify_item(source_item, migrated)
        if mismatches:
            problems.append(f"{item_id}: field(s) {', '.join(mismatches)} differ from source")

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1

    print(f"-- verify: {len(sources)} item(s) byte-identical to source --", file=out)
    return 0


def run_commit_cleanup(work_dir, out=None):
    out = out or sys.stdout
    items_dir = os.path.join(work_dir, "items")
    if not os.path.isdir(items_dir) or not os.listdir(items_dir):
        raise RuntimeError("work/items/ does not exist yet — run --commit first")

    renamed = []
    for name in ("backlog.json", "wip.json"):
        src = os.path.join(work_dir, name)
        if not os.path.exists(src):
            continue
        dst = f"{src}.pre-migration.bak"
        if os.path.exists(dst):
            raise RuntimeError(
                f"{dst} already exists — refusing to overwrite; remove or "
                "rename it manually if this is intentional")
        os.replace(src, dst)
        renamed.append(name)

    print(f"-- renamed {', '.join(renamed) or 'nothing'} to *.pre-migration.bak --", file=out)
    return 0


def main():
    mode = os.environ.get("MODE_ENV", "").strip()
    work_dir = os.environ.get("WORK_DIR_ENV", "").strip()
    work_sessions_repo = os.environ.get("WORK_SESSIONS_REPO_ENV", "").strip()

    if not work_dir:
        print("migrate-items-v2: WORK_DIR_ENV is required", file=sys.stderr)
        return 2

    try:
        if mode == "dry-run":
            return run_dry_run(work_dir, work_sessions_repo)
        if mode == "commit":
            fault_id = os.environ.get("MIGRATE_FAULT_CORRUPT_ID_ENV", "").strip() or None
            fault_final_move = os.environ.get("MIGRATE_FAULT_FAIL_FINAL_MOVE_ENV", "").strip() == "1"
            return run_commit(work_dir, work_sessions_repo, _fault_inject_id=fault_id,
                              _fault_fail_final_move=fault_final_move)
        if mode == "commit-cleanup":
            return run_commit_cleanup(work_dir)
        if mode == "verify":
            return run_verify(work_dir)
        print(f"migrate-items-v2: unknown mode {mode!r}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"migrate-items-v2: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
