#!/usr/bin/env python3
"""Pure item-shaping logic for the canonical Work Item constructor
(scripts/define-work-item.sh).

This is the ONE place a Work Item's fields get shaped — every caller
(#triage-inbox, #groom-item, init-session.sh's upsert path) goes through
this instead of duplicating shaping logic, which is what keeps field names
(e.g. `scope`, not a mix of `scope`/`weight`) from drifting between callers.
See work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md §1, §3.

Behaviour:
- Only fields explicitly passed (non-None/non-empty) are changed; everything
  else on an existing item — including `sessions[]`, `history`,
  `current_state`, `roadmap` — is preserved untouched.
- A brand new item gets `current_state`/`history`/`sessions` initialized;
  reshaping an existing item never touches those three (they are owned by
  the session lifecycle, not the constructor).
- `status` and `scope` are validated against fixed enums — a typo is caught
  here, once, rather than drifting into the store.

Inputs come from the environment (set by define-work-item.sh) so nothing has
to be shell-quoted, mirroring scripts/lib/upsert_wip.py's convention:
`ITEM_ID_ENV`, `ITEM_FILE_ENV`, `TITLE_ENV`, `DESCRIPTION_ENV`, `STATUS_ENV`,
`PRIORITY_ENV`, `SCOPE_ENV`, `TICKET_ENV`, `TASK_TYPE_ENV`, `NOW_ENV`,
`RECORD_EVENT_ENV`, `EVENT_BY_ENV`, `CURRENT_STATE_DESCRIPTION_ENV`,
`CURRENT_STATE_BLOCKED_ENV`, `LAST_SYNCED_ENV`, `OPEN_EPISODE_ENV`,
`CLOSE_EPISODE_ENV`, `OUTCOME_ENV`, `PARENT_ID_ENV`, `PROMOTE_ENV`.

The decision-making logic lives in :func:`define_item` (pure — takes dicts,
returns dicts) so it can be unit-tested without touching the filesystem;
only :func:`main` does I/O. Locking is the caller's (the shell wrapper's)
responsibility — this module assumes it already holds the item's lock.

ADH-012's one exception to "only main does I/O": :func:`validate_parent_link`
reads other items' files to check the one-level-deep hierarchy invariant,
which a pure function fundamentally can't do. The caller (the `.sh`
wrapper) must hold the shared `work/items/.parent-link.lock/` for the
whole validate-then-write sequence — see SPEC.md §4 for why an unguarded
read here is unsafe in a way ordinary advisory pre-checks in this codebase
are not.
"""
import json
import os
import sys

VALID_STATUSES = {"grooming", "ready", "in progress", "on hold", "in review", "done"}
VALID_EPISODE_OUTCOMES = {"done", "stopped", "paused"}
VALID_SCOPES = {"XS", "S", "M", "L", "XL"}


def _load(path):
    """Load a JSON object from ``path``; a missing/blank file means "no
    existing item" (``None``), distinct from ``{}`` which would be a real,
    empty item. Raises ``ValueError`` if the file exists but isn't a JSON
    object, so a corrupt item file is surfaced loudly rather than silently
    overwritten."""
    if not path or not os.path.exists(path):
        return None
    with open(path) as fh:
        text = fh.read().strip()
    if not text:
        return None
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def _dump(path, data):
    """Write ``data`` to ``path`` as pretty-printed JSON, atomically
    (tmp file + rename) so a reader never observes a partial write."""
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _seed_title(description, task_type):
    description = (description or "").strip()
    if task_type:
        return f"[{task_type}] {description}"
    return description


_CLOSED_LIKE_STATUSES = {"done", "on hold", "in review"}


def _ensure_episode_1(item, now):
    """Return ``item``'s ``sessions[]``, normalized: every entry gets an
    explicit ``outcome`` key (defaulting to ``None`` — the already-shipped
    ADH-008 migration entries have no such key at all, and this is the only
    "migration" they get, applied lazily on read rather than rewritten
    up front). If ``sessions[]`` is structurally empty (an item that never
    had a SESSIONS_STATE.md row at ADH-008 migration time — see SPEC.md
    sec.2; currently unreachable by any live item through the designed
    reopen entry point, but a real defensive case), synthesize episode 1's
    entry from the item's own ``history`` first.

    Never mutates ``item`` or its nested dicts — returns a new list of new
    dicts, matching this module's pure-function-in/out discipline."""
    sessions = item.get("sessions") or []
    if sessions:
        return [dict(e, outcome=e.get("outcome")) for e in sessions]

    history = item.get("history") or []
    opened = None
    for h in history:
        if h.get("action") in ("item defined", "session started"):
            opened = h.get("timestamp")
            break

    status = item.get("status")
    closed = None
    outcome = None
    if status in _CLOSED_LIKE_STATUSES:
        outcome = status
        if history:
            closed = history[-1].get("timestamp")

    item_id = item.get("id")
    return [{
        "episode_id": item_id,
        "episode_number": 1,
        "folder": f"sessions/{item_id}",
        "opened": opened,
        "closed": closed,
        "outcome": outcome,
    }]


def validate_parent_link(items_dir, item_id, parent_id):
    """Raise ``ValueError`` with a precise, user-facing reason if linking
    ``item_id`` under ``parent_id`` would violate the one-level-deep
    hierarchy invariant (ADH-012 SPEC.md §2/§4); return ``None`` if the
    link is valid.

    The caller MUST hold the shared ``work/items/.parent-link.lock/`` for
    the whole validate-then-write sequence this feeds into — this function
    reads ``items_dir`` unguarded, and an unlocked caller reintroduces the
    exact multi-level-chain race the lock exists to close (see SPEC.md §4).
    """
    if parent_id == item_id:
        raise ValueError(f"an item cannot be its own parent: {item_id!r}")

    parent_item = _load(os.path.join(items_dir, f"{parent_id}.json"))
    if parent_item is None:
        raise ValueError(
            f"no such item: {parent_id!r} — cannot link {item_id!r} to a nonexistent parent")
    if parent_item.get("parent_id"):
        raise ValueError(
            f"{parent_id!r} already has a parent ({parent_item['parent_id']!r}) — "
            "this system supports exactly one level of nesting, so it can't also become one")

    if os.path.isdir(items_dir):
        for fname in os.listdir(items_dir):
            if not fname.endswith(".json"):
                continue
            other_id = fname[:-len(".json")]
            if other_id in (item_id, parent_id):
                continue
            other = _load(os.path.join(items_dir, fname))
            if other and other.get("parent_id") == item_id:
                raise ValueError(
                    f"{item_id!r} already has sub-items of its own (e.g. {other_id!r}) — "
                    "can't also become a sub-item; this system supports exactly one level of nesting")

    return None


def validate_promote(items_dir, item_id):
    """Raise ``ValueError`` if ``item_id`` has no ``parent_id`` to clear —
    ``--promote`` refuses rather than silently no-opping, since a
    zero-effect promote is the likely signature of promoting the wrong id
    (ADH-012 SPEC.md §3). Return ``None`` if the item genuinely has a
    parent to clear."""
    item = _load(os.path.join(items_dir, f"{item_id}.json"))
    if item is None or not item.get("parent_id"):
        raise ValueError(f"{item_id!r} has no parent_id to clear — nothing to promote")
    return None


def define_item(existing, *, item_id, title=None, description=None, status=None,
                 priority=None, scope=None, ticket=None, task_type=None, now=None,
                 record_event=None, event_by="define-work-item.sh",
                 current_state_description=None, current_state_blocked=False,
                 last_synced=None, open_episode=None, close_episode=None,
                 parent_id=None, promote=False):
    """Return the shaped item dict for ``item_id``, merged onto ``existing``
    (``None`` for a brand new item). Pure — no I/O.

    Raises ``ValueError`` if ``status`` or ``scope`` is passed but not one of
    the recognized values.

    ``record_event``/``event_by``/``current_state_description``/
    ``current_state_blocked`` are the explicit, opt-in way for a caller that
    needs to record a discrete event (``init-session.sh``: "session
    started"; ``#triage-inbox``: "Triaged from INBOX") to do so through this
    SAME locked write path — reshaping otherwise never touches
    history/current_state (see the ``else`` branch below), by design, so a
    plain field-reshaping call can never clobber them unless it explicitly
    asks not to be. Applies regardless of ``is_new``, and regardless of
    whether other fields were also reshaped in the same call.

    ``last_synced``: the batched-close-checkpoint watermark
    (``#end_work_session.prompt.md``, ADH-008 Phase 8) — set only when
    explicitly passed; absent/unset otherwise, and never reset by an
    unrelated reshape.

    ``open_episode``/``close_episode`` (ADH-011): the same opt-in pattern as
    ``record_event``/``current_state_*`` — an ordinary reshape call never
    touches ``sessions[]``. ``open_episode`` is the new episode's session id
    (``<item-id>--e<N>``); ``close_episode`` is a ``(session_id, outcome)``
    pair. Both raise ``ValueError`` on a bad call (opening while the last
    episode is still open; closing an outcome-less call; closing a session
    id with no matching entry). See SPEC.md sec.2/3 for the full design,
    including the lazy structurally-empty-sessions backfill.

    ``parent_id``/``promote`` (ADH-012): plain reshape-tier fields, not the
    session-lifecycle opt-in kind — ``parent_id`` sets the field, ``promote``
    clears it (removes the key entirely). Raises ``ValueError`` if both are
    passed together. This function does NOT validate a parent link (no
    self-parent / no two-level-chain / not-already-a-parent checks) — that
    requires reading OTHER items' files, which a pure function can't do; see
    :func:`validate_parent_link`, called by the caller before this function
    is ever invoked. The check here is deliberately duplicated (not
    redundant) because this function is also exercised directly by its own
    test suite, not only through the wrapper that runs the real validation.
    """
    is_new = existing is None
    item = dict(existing) if existing else {}
    item["id"] = item_id

    if title:
        item["title"] = title
    elif is_new:
        item["title"] = _seed_title(description, task_type)

    if description is not None:
        item["description"] = description

    if status:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status!r} (expected one of {sorted(VALID_STATUSES)})")
        item["status"] = status
    elif is_new:
        item["status"] = "grooming"

    if priority:
        item["priority"] = priority

    if scope:
        if scope not in VALID_SCOPES:
            raise ValueError(f"invalid scope: {scope!r} (expected one of {sorted(VALID_SCOPES)})")
        item["scope"] = scope

    if ticket:
        tickets = dict(item.get("tickets") or {})
        tickets["main-bug-tracking"] = ticket
        item["tickets"] = tickets

    if is_new:
        item["current_state"] = {
            "description": (description or item.get("title") or "").strip(),
            "is_blocked": False,
        }
        item["history"] = [{
            "action": "item defined",
            "timestamp": now,
            "by": "define-work-item.sh",
        }]
        item["sessions"] = []
    else:
        # Reshaping never touches these three — they're owned by the session
        # lifecycle. Only backfill if genuinely absent (legacy pre-migration
        # items), never reset an existing value.
        item.setdefault("history", [])
        item.setdefault("sessions", [])
        item.setdefault("current_state", {
            "description": item.get("description", ""),
            "is_blocked": False,
        })

    if record_event:
        history = list(item.get("history") or [])
        history.append({"action": record_event, "timestamp": now, "by": event_by})
        item["history"] = history

    if current_state_description is not None:
        item["current_state"] = {
            "description": current_state_description,
            "is_blocked": bool(current_state_blocked),
        }

    if last_synced is not None:
        item["last_synced"] = last_synced

    if open_episode:
        sessions = _ensure_episode_1(item, now)
        if sessions[-1]["closed"] is None:
            raise ValueError(
                f"cannot open a new episode: {sessions[-1]['episode_id']!r} is still open")
        next_number = max(e["episode_number"] for e in sessions) + 1
        sessions.append({
            "episode_id": open_episode,
            "episode_number": next_number,
            "folder": f"sessions/{open_episode}",
            "opened": now,
            "closed": None,
            "outcome": None,
        })
        item["sessions"] = sessions
        item["status"] = "in progress"
        history = list(item.get("history") or [])
        history.append({
            "action": f"reopened as episode {next_number}",
            "timestamp": now, "by": event_by,
        })
        item["history"] = history

    if close_episode:
        session_id, outcome = close_episode
        if not outcome:
            raise ValueError("close_episode requires a non-empty outcome")
        if outcome not in VALID_EPISODE_OUTCOMES:
            raise ValueError(
                f"invalid episode outcome: {outcome!r} (expected one of {sorted(VALID_EPISODE_OUTCOMES)})")
        sessions = _ensure_episode_1(item, now)
        match = next((e for e in sessions if e["episode_id"] == session_id), None)
        if match is None:
            raise ValueError(f"no episode found for session id: {session_id!r}")
        if match is not sessions[-1]:
            raise ValueError(
                f"cannot close {session_id!r}: it is not the most recent episode "
                f"({sessions[-1]['episode_id']!r} is — closing an older episode out of "
                "order would leave the item's status inconsistent with its actual last episode)")
        match["closed"] = now
        match["outcome"] = outcome
        item["sessions"] = sessions
        if outcome == "done":
            item["status"] = "done"
        history = list(item.get("history") or [])
        history.append({
            "action": f"closed episode {match['episode_number']} (outcome: {outcome})",
            "timestamp": now, "by": event_by,
        })
        item["history"] = history

    if parent_id and promote:
        raise ValueError("parent_id and promote are mutually exclusive")
    if parent_id:
        item["parent_id"] = parent_id
    elif promote:
        item.pop("parent_id", None)

    return item


def main():
    item_id = os.environ.get("ITEM_ID_ENV", "").strip()
    if not item_id:
        print("define-work-item: ITEM_ID_ENV is required", file=sys.stderr)
        return 2

    item_file = os.environ.get("ITEM_FILE_ENV", "").strip()
    if not item_file:
        print("define-work-item: ITEM_FILE_ENV is required", file=sys.stderr)
        return 2

    try:
        existing = _load(item_file)
        item = define_item(
            existing,
            item_id=item_id,
            title=os.environ.get("TITLE_ENV") or None,
            description=os.environ.get("DESCRIPTION_ENV") or None,
            status=os.environ.get("STATUS_ENV") or None,
            priority=os.environ.get("PRIORITY_ENV") or None,
            scope=os.environ.get("SCOPE_ENV") or None,
            ticket=os.environ.get("TICKET_ENV") or None,
            task_type=os.environ.get("TASK_TYPE_ENV") or None,
            now=os.environ.get("NOW_ENV", ""),
            record_event=os.environ.get("RECORD_EVENT_ENV") or None,
            event_by=os.environ.get("EVENT_BY_ENV") or "define-work-item.sh",
            current_state_description=os.environ.get("CURRENT_STATE_DESCRIPTION_ENV") or None,
            current_state_blocked=os.environ.get("CURRENT_STATE_BLOCKED_ENV", "") == "1",
            last_synced=os.environ.get("LAST_SYNCED_ENV") or None,
            open_episode=os.environ.get("OPEN_EPISODE_ENV") or None,
            close_episode=(
                (os.environ.get("CLOSE_EPISODE_ENV"), os.environ.get("OUTCOME_ENV", ""))
                if os.environ.get("CLOSE_EPISODE_ENV") else None
            ),
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"define-work-item: {exc}", file=sys.stderr)
        return 1

    _dump(item_file, item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
