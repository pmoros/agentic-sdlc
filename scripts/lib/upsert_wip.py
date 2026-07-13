#!/usr/bin/env python3
"""Upsert a session's entry into the portfolio work tracker (work/wip.json).

Backs the wip-registration step of ``init-session.sh``: when a work session is
started, the framework must guarantee a matching ``in progress`` item exists in
the portfolio work tracker, so a started session can never leave
``work/backlog.json`` / ``work/wip.json`` as empty placeholders.

Behaviour (the "upsert"):
- Keyed by the session id.
- If the id already exists in ``work/backlog.json``, **move** it to wip:
  its groomed fields (title/description/tickets/work_items/resources/roadmap)
  are preserved, and it is removed from the backlog.
- Otherwise a **fresh** wip entry is seeded from the session's
  goal/ticket/scope/task-type.
- The entry's ``status`` is forced to ``in progress``, ``current_state`` is
  set, and a "session started" line is appended to the append-only ``history``.
- **Idempotent**: if the id is already in wip, its ``history`` is left intact
  (no duplicate "session started" entry) and other entries are never touched.
- Output is valid, pretty-printed JSON.

Inputs come from the environment (set by ``init-session.sh``) so nothing has to
be shell-quoted: ``SID_ENV``, ``GOAL_ENV``, ``TICKET_ENV``, ``SCOPE_ENV``,
``TASK_TYPE_ENV``, ``BLOCKERS_ENV``, ``NOW_ENV``, ``WIP_JSON_ENV``,
``BACKLOG_JSON_ENV``.

The decision-making logic lives in :func:`upsert_wip` (pure — takes dicts,
returns dicts) so it can be unit-tested without touching the filesystem; only
:func:`main` does I/O.
"""
import json
import os
import sys


def _load(path):
    """Load a JSON object from ``path``; treat a missing/blank file as ``{}``.

    Raises ``ValueError`` if the file exists but does not hold a JSON object,
    so a corrupt tracker is surfaced loudly rather than silently overwritten.
    """
    if not path or not os.path.exists(path):
        return {}
    with open(path) as fh:
        text = fh.read().strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def _dump(path, data):
    """Write ``data`` to ``path`` as pretty-printed JSON with a trailing newline."""
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def _seed_title(goal, task_type):
    """Build a fresh item title from the session goal (+ optional task-type tag)."""
    goal = (goal or "").strip()
    if task_type:
        return f"[{task_type}] {goal}"
    return goal


def upsert_wip(wip, backlog, *, sid, goal, ticket="", scope="",
               task_type="", blockers="", now=""):
    """Return ``(wip, backlog)`` with ``sid`` registered as an in-progress item.

    Pure: takes and returns plain dicts, performs no I/O. Idempotent — if
    ``sid`` is already in ``wip`` it is returned unchanged (other than being a
    fresh copy) so re-running never duplicates history or clobbers progress.
    """
    wip = dict(wip)
    backlog = dict(backlog)

    if sid in wip:
        # Already registered — do not touch it (append-only history, live
        # current_state). This is what makes the upsert idempotent.
        return wip, backlog

    if sid in backlog:
        # Move the groomed backlog item into wip, preserving its shaped fields.
        item = dict(backlog.pop(sid))
    else:
        # Seed a fresh item from the session details.
        item = {
            "title": _seed_title(goal, task_type),
            "description": (goal or "").strip(),
        }
        if ticket:
            item["tickets"] = {"main-bug-tracking": ticket}
        if scope:
            item["scope"] = scope

    is_blocked = bool((blockers or "").strip())
    item["status"] = "in progress"
    item["current_state"] = {
        "description": (blockers.strip() if is_blocked else (goal or "").strip()),
        "is_blocked": is_blocked,
    }

    history = list(item.get("history") or [])
    history.append({
        "action": "session started",
        "timestamp": now,
        "by": "init-session.sh",
    })
    item["history"] = history

    wip[sid] = item
    return wip, backlog


def main():
    sid = os.environ.get("SID_ENV", "").strip()
    if not sid:
        print("upsert_wip: SID_ENV is required", file=sys.stderr)
        return 2

    wip_path = os.environ.get("WIP_JSON_ENV", "")
    backlog_path = os.environ.get("BACKLOG_JSON_ENV", "")

    wip = _load(wip_path)
    backlog = _load(backlog_path)

    wip, backlog = upsert_wip(
        wip, backlog,
        sid=sid,
        goal=os.environ.get("GOAL_ENV", ""),
        ticket=os.environ.get("TICKET_ENV", ""),
        scope=os.environ.get("SCOPE_ENV", ""),
        task_type=os.environ.get("TASK_TYPE_ENV", ""),
        blockers=os.environ.get("BLOCKERS_ENV", ""),
        now=os.environ.get("NOW_ENV", ""),
    )

    _dump(wip_path, wip)
    # Only rewrite the backlog if it exists (a move may have mutated it).
    if backlog_path and os.path.exists(backlog_path):
        _dump(backlog_path, backlog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
