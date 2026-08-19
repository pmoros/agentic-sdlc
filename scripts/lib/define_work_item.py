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
`PRIORITY_ENV`, `SCOPE_ENV`, `TICKET_ENV`, `TASK_TYPE_ENV`, `NOW_ENV`.

The decision-making logic lives in :func:`define_item` (pure — takes dicts,
returns dicts) so it can be unit-tested without touching the filesystem;
only :func:`main` does I/O. Locking is the caller's (the shell wrapper's)
responsibility — this module assumes it already holds the item's lock.
"""
import json
import os
import sys

VALID_STATUSES = {"grooming", "ready", "in progress", "on hold", "in review", "done"}
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


def define_item(existing, *, item_id, title=None, description=None, status=None,
                 priority=None, scope=None, ticket=None, task_type=None, now=None,
                 record_event=None, event_by="define-work-item.sh",
                 current_state_description=None, current_state_blocked=False):
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
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"define-work-item: {exc}", file=sys.stderr)
        return 1

    _dump(item_file, item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
