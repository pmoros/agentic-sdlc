#!/usr/bin/env python3
"""Pure view-partitioning logic for regenerate-views.sh.

`work/backlog.json` / `wip.json` / `archive.json` are generated, read-only
indexes over `work/items/*.json` — never hand-edited. This module holds the
partitioning rule (item status -> which view) as a pure function so it can
be unit-tested without touching the filesystem; `regenerate-views.sh` does
the directory scan, `--check` comparison, and atomic file writes.
See work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md §2.

`work/scratchpad.json` is explicitly out of scope — it is a separate,
manually-edited, pre-item store (see SPEC.md Constraints) and is never
touched by this module or by regenerate-views.sh.
"""
import json
import os
import sys
import tempfile

# The item-status enum (work-item.schema.json / README "Status values").
# Note: SPEC.md's original partition table also mentioned a `stopped`
# status landing in archive — but `stopped` is not a real Work Item status
# (it's a Session/episode-level status in SESSIONS_STATE.md, a different
# enum). Only `done` items land in archive; corrected here during
# implementation rather than propagated from that table verbatim.
STATUS_TO_VIEW = {
    "grooming": "backlog",
    "ready": "backlog",
    "in progress": "wip",
    "on hold": "wip",
    "in review": "wip",
    "done": "archive",
}

VIEW_NAMES = ("backlog", "wip", "archive")

_ENTRY_FIELDS = ("title", "status", "priority", "scope")


def _summarize(item):
    """Lightweight index entry: title/status always, priority/scope only
    when present on the item. Deliberately NOT the full item — description,
    history, sessions, current_state, roadmap, tickets stay in the item's
    own file under work/items/."""
    return {k: item[k] for k in _ENTRY_FIELDS if k in item}


def partition_items(items):
    """Return ``{"backlog": {...}, "wip": {...}, "archive": {...}}``, each a
    dict of ``{item_id: lightweight_entry}``. Pure — no I/O.

    Raises ``ValueError`` on an item with a status outside the recognized
    enum — a bad status should fail the regeneration loudly, not silently
    drop the item from every view.
    """
    views = {name: {} for name in VIEW_NAMES}
    for item_id, item in items.items():
        status = item.get("status")
        try:
            view = STATUS_TO_VIEW[status]
        except KeyError:
            raise ValueError(
                f"item {item_id!r} has unrecognized status {status!r} "
                f"(expected one of {sorted(STATUS_TO_VIEW)})"
            )
        views[view][item_id] = _summarize(item)
    return views


def _dump(path, data):
    """Write ``data`` to ``path`` atomically (tmp file + rename).

    Unlike ``work/items/<id>.json`` (locked per-item, so exactly one writer
    ever targets a given item file), the three view files ARE a shared
    target — regenerate-views.sh can legitimately run concurrently from
    several `define-work-item.sh` invocations touching different items. A
    fixed tmp filename let two such writers race: one's `os.replace` could
    rename the tmp file away just before the other tried to replace it,
    raising `FileNotFoundError` and failing an otherwise-successful item
    write. `tempfile.mkstemp` in the same directory gives each writer its
    own tmp file, so concurrent writers never collide — worst case is
    last-writer-wins on the view content itself, which is fine (harmless,
    self-heals on the next write) since the source of truth is
    `work/items/*.json`, never the views."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(
        prefix=f"{os.path.basename(path)}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _load_view(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path) as fh:
        text = fh.read().strip()
    return json.loads(text) if text else {}


def _scan_items(items_dir):
    """Load every `work/items/<id>.json` into `{id: item}`. Skips `.tmp`
    files (an in-flight atomic write) and anything that isn't a regular
    `.json` file (e.g. a `.lock` directory)."""
    items = {}
    if not os.path.isdir(items_dir):
        return items
    for name in sorted(os.listdir(items_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(items_dir, name)
        if not os.path.isfile(path):
            continue
        with open(path) as fh:
            text = fh.read().strip()
        if not text:
            continue
        item = json.loads(text)
        items[item.get("id", name[: -len(".json")])] = item
    return items


def main():
    items_dir = os.environ.get("ITEMS_DIR_ENV", "").strip()
    if not items_dir:
        print("regenerate-views: ITEMS_DIR_ENV is required", file=sys.stderr)
        return 2

    view_paths = {
        "backlog": os.environ.get("BACKLOG_JSON_ENV", ""),
        "wip": os.environ.get("WIP_JSON_ENV", ""),
        "archive": os.environ.get("ARCHIVE_JSON_ENV", ""),
    }
    if not all(view_paths.values()):
        print("regenerate-views: BACKLOG_JSON_ENV, WIP_JSON_ENV, and "
              "ARCHIVE_JSON_ENV are all required", file=sys.stderr)
        return 2

    check_mode = os.environ.get("CHECK_ENV", "") == "1"

    try:
        items = _scan_items(items_dir)
        expected = partition_items(items)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"regenerate-views: {exc}", file=sys.stderr)
        return 1

    if check_mode:
        drift = []
        for name in VIEW_NAMES:
            actual = _load_view(view_paths[name])
            if actual != expected[name]:
                drift.append(name)
        if drift:
            print(
                "regenerate-views --check: drift detected in "
                f"{', '.join(drift)} — these views don't match "
                "work/items/*.json. Run regenerate-views.sh (no --check) "
                "to fix, or investigate a hand-edit.",
                file=sys.stderr,
            )
            return 1
        print("regenerate-views --check: views are up to date", file=sys.stderr)
        return 0

    for name in VIEW_NAMES:
        _dump(view_paths[name], expected[name])
    return 0


if __name__ == "__main__":
    sys.exit(main())
