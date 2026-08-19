"""Unit tests for the pure item-shaping logic (scripts/lib/define_work_item.py).

Tests the decision-making function directly with plain dicts — no filesystem,
no subprocess, no locking. The end-to-end wiring through define-work-item.sh
(locking, file I/O, CLI validation) is covered in test_define_work_item_sh.py.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import define_work_item as D  # noqa: E402

NOW = "2026-08-18T10:00:00Z"


class CreateFreshItem(unittest.TestCase):
    def test_seeds_title_from_description_and_task_type_when_no_title_given(self):
        item = D.define_item(
            None, item_id="ADH-9", description="Do a thing",
            task_type="feat", now=NOW)
        self.assertEqual(item["title"], "[feat] Do a thing")
        self.assertEqual(item["description"], "Do a thing")

    def test_explicit_title_wins_over_seeded_title(self):
        item = D.define_item(
            None, item_id="ADH-9", title="Explicit Title",
            description="Do a thing", task_type="feat", now=NOW)
        self.assertEqual(item["title"], "Explicit Title")

    def test_defaults_status_to_grooming(self):
        item = D.define_item(None, item_id="ADH-9", description="d", now=NOW)
        self.assertEqual(item["status"], "grooming")

    def test_explicit_status_is_honored(self):
        item = D.define_item(
            None, item_id="ADH-9", description="d", status="ready", now=NOW)
        self.assertEqual(item["status"], "ready")

    def test_sets_scope_and_priority_and_ticket(self):
        item = D.define_item(
            None, item_id="ADH-9", description="d", scope="M",
            priority="Major", ticket="https://x/browse/ADH-9", now=NOW)
        self.assertEqual(item["scope"], "M")
        self.assertEqual(item["priority"], "Major")
        self.assertEqual(item["tickets"], {"main-bug-tracking": "https://x/browse/ADH-9"})

    def test_initializes_current_state_history_and_sessions(self):
        item = D.define_item(None, item_id="ADH-9", description="Do a thing", now=NOW)
        self.assertEqual(item["current_state"], {"description": "Do a thing", "is_blocked": False})
        self.assertEqual(item["sessions"], [])
        self.assertEqual(len(item["history"]), 1)
        self.assertEqual(item["history"][0]["action"], "item defined")
        self.assertEqual(item["history"][0]["timestamp"], NOW)
        self.assertEqual(item["history"][0]["by"], "define-work-item.sh")

    def test_id_field_always_set_to_item_id(self):
        item = D.define_item(None, item_id="ADH-9", description="d", now=NOW)
        self.assertEqual(item["id"], "ADH-9")


class ValidationRejectsUnknownValues(unittest.TestCase):
    def test_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            D.define_item(None, item_id="ADH-9", description="d", status="bogus", now=NOW)

    def test_rejects_unknown_scope(self):
        with self.assertRaises(ValueError):
            D.define_item(None, item_id="ADH-9", description="d", scope="huge", now=NOW)

    def test_every_documented_status_is_accepted(self):
        for status in ("grooming", "ready", "in progress", "on hold", "in review", "done"):
            item = D.define_item(None, item_id="ADH-9", description="d", status=status, now=NOW)
            self.assertEqual(item["status"], status)

    def test_every_documented_scope_is_accepted(self):
        for scope in ("XS", "S", "M", "L", "XL"):
            item = D.define_item(None, item_id="ADH-9", description="d", scope=scope, now=NOW)
            self.assertEqual(item["scope"], scope)


class ReshapeExistingItem(unittest.TestCase):
    def _existing(self):
        return {
            "id": "PROJ-1",
            "title": "Groomed title",
            "description": "shaped",
            "status": "ready",
            "scope": "M",
            "current_state": {"description": "waiting on review", "is_blocked": True},
            "history": [{"action": "groomed", "timestamp": "2026-08-01", "by": "pm"}],
            "sessions": [{"episode_id": "PROJ-1", "episode_number": 1}],
            "roadmap": [{"step": "s1", "owner": "me"}],
        }

    def test_only_explicitly_passed_fields_change(self):
        item = D.define_item(self._existing(), item_id="PROJ-1", status="in progress", now=NOW)
        self.assertEqual(item["status"], "in progress")        # changed
        self.assertEqual(item["title"], "Groomed title")       # untouched
        self.assertEqual(item["scope"], "M")                    # untouched
        self.assertEqual(item["roadmap"], [{"step": "s1", "owner": "me"}])  # untouched

    def test_does_not_reseed_title_from_description_when_item_exists(self):
        item = D.define_item(
            self._existing(), item_id="PROJ-1", description="new description",
            task_type="feat", now=NOW)
        self.assertEqual(item["title"], "Groomed title")       # NOT re-seeded to "[feat] ..."
        self.assertEqual(item["description"], "new description")

    def test_history_is_append_only_not_reset(self):
        item = D.define_item(self._existing(), item_id="PROJ-1", status="in progress", now=NOW)
        actions = [h["action"] for h in item["history"]]
        self.assertEqual(actions, ["groomed"])                  # no new entry added by the constructor itself

    def test_current_state_and_sessions_untouched_by_reshape(self):
        item = D.define_item(self._existing(), item_id="PROJ-1", priority="Critical", now=NOW)
        self.assertEqual(item["current_state"], {"description": "waiting on review", "is_blocked": True})
        self.assertEqual(item["sessions"], [{"episode_id": "PROJ-1", "episode_number": 1}])

    def test_ticket_merges_into_existing_tickets_map(self):
        existing = self._existing()
        existing["tickets"] = {"design-doc": "https://wiki/design"}
        item = D.define_item(existing, item_id="PROJ-1", ticket="https://x/browse/PROJ-1", now=NOW)
        self.assertEqual(item["tickets"], {
            "design-doc": "https://wiki/design",
            "main-bug-tracking": "https://x/browse/PROJ-1",
        })

    def test_reshape_with_no_fields_passed_is_a_no_op_besides_id(self):
        existing = self._existing()
        item = D.define_item(dict(existing), item_id="PROJ-1", now=NOW)
        existing["id"] = "PROJ-1"
        self.assertEqual(item, existing)


class LifecycleEventOptIn(unittest.TestCase):
    """ADH-008 Phase 7: reshaping normally never touches history/current_state
    (owned by the session lifecycle, not the constructor — see
    ReshapeExistingItem above). `record_event`/`current_state_*` are the
    explicit, opt-in override a session-lifecycle caller (init-session.sh)
    uses to record its own event through the same locked write path,
    instead of a second script racing on the same file."""

    def _existing(self):
        return {
            "id": "PROJ-1", "title": "t", "description": "d", "status": "ready",
            "current_state": {"description": "old", "is_blocked": False},
            "history": [{"action": "groomed", "timestamp": "2026-08-01", "by": "pm"}],
            "sessions": [],
        }

    def test_record_event_appends_history_even_on_reshape(self):
        item = D.define_item(
            self._existing(), item_id="PROJ-1", status="in progress",
            record_event="session started", event_by="init-session.sh", now=NOW)
        actions = [h["action"] for h in item["history"]]
        self.assertEqual(actions, ["groomed", "session started"])
        self.assertEqual(item["history"][-1]["by"], "init-session.sh")
        self.assertEqual(item["history"][-1]["timestamp"], NOW)

    def test_record_event_defaults_by_to_script_name(self):
        item = D.define_item(self._existing(), item_id="PROJ-1", record_event="x", now=NOW)
        self.assertEqual(item["history"][-1]["by"], "define-work-item.sh")

    def test_no_record_event_leaves_history_untouched(self):
        item = D.define_item(self._existing(), item_id="PROJ-1", status="in progress", now=NOW)
        self.assertEqual(len(item["history"]), 1)

    def test_current_state_description_overwrites_on_reshape(self):
        item = D.define_item(
            self._existing(), item_id="PROJ-1",
            current_state_description="new state", now=NOW)
        self.assertEqual(item["current_state"], {"description": "new state", "is_blocked": False})

    def test_current_state_blocked_flag(self):
        item = D.define_item(
            self._existing(), item_id="PROJ-1",
            current_state_description="waiting", current_state_blocked=True, now=NOW)
        self.assertEqual(item["current_state"], {"description": "waiting", "is_blocked": True})

    def test_fresh_item_gets_both_item_defined_and_the_recorded_event(self):
        # A brand-new item created via a lifecycle call (e.g. init-session.sh
        # registering a session with no prior groomed backlog entry) gets
        # BOTH the constructor's own "item defined" entry AND the caller's
        # event — more granular than the old upsert_wip.py behavior, not a
        # regression (see scripts/README.md test note for this class).
        item = D.define_item(
            None, item_id="ADH-9", description="fresh", status="in progress",
            record_event="session started", event_by="init-session.sh", now=NOW)
        actions = [h["action"] for h in item["history"]]
        self.assertEqual(actions, ["item defined", "session started"])


class LastSyncedWatermark(unittest.TestCase):
    """ADH-008 Phase 8: end_work_session's batched close-checkpoint records
    a `last_synced` watermark on the item after a successful external-write
    batch, through this same locked write path — same opt-in pattern as
    record_event, since it's a lifecycle-event field, not a shapeable one."""

    def test_last_synced_sets_the_field(self):
        item = D.define_item(
            {"id": "PROJ-1", "title": "t", "status": "in progress",
             "current_state": {"description": "d", "is_blocked": False},
             "history": [], "sessions": []},
            item_id="PROJ-1", last_synced="2026-08-19T00:00:00Z", now=NOW)
        self.assertEqual(item["last_synced"], "2026-08-19T00:00:00Z")

    def test_no_last_synced_leaves_field_absent_on_fresh_item(self):
        item = D.define_item(None, item_id="ADH-9", description="d", now=NOW)
        self.assertNotIn("last_synced", item)

    def test_no_last_synced_leaves_existing_value_untouched_on_reshape(self):
        item = D.define_item(
            {"id": "PROJ-1", "title": "t", "status": "in progress",
             "current_state": {"description": "d", "is_blocked": False},
             "history": [], "sessions": [], "last_synced": "2026-08-01T00:00:00Z"},
            item_id="PROJ-1", priority="Major", now=NOW)
        self.assertEqual(item["last_synced"], "2026-08-01T00:00:00Z")

    def test_last_synced_combines_with_record_event(self):
        item = D.define_item(
            {"id": "PROJ-1", "title": "t", "status": "in progress",
             "current_state": {"description": "d", "is_blocked": False},
             "history": [], "sessions": []},
            item_id="PROJ-1", record_event="session ended", event_by="end_work_session",
            last_synced="2026-08-19T00:00:00Z", now=NOW)
        self.assertEqual(item["last_synced"], "2026-08-19T00:00:00Z")
        self.assertEqual(item["history"][-1]["action"], "session ended")


class EpisodeLifecycle(unittest.TestCase):
    """ADH-011: reopen a done/on-hold/in-review item as a new episode.
    `sessions[]` entries use the shape ADH-008's migrate_items.py already
    shipped (episode_id/episode_number/folder/opened/closed), extended with
    one new `outcome` field — see SPEC.md sec.2. Both flags are the same
    opt-in pattern as record_event/current_state: an ordinary reshape call
    never touches sessions[]."""

    def _populated(self, status="done", closed="2026-08-01T00:00:00Z", outcome=None):
        entry = {
            "episode_id": "ADH-4", "episode_number": 1,
            "folder": "sessions/ADH-4", "opened": "2026-07-01T00:00:00Z",
            "closed": closed,
        }
        if outcome is not None:
            entry["outcome"] = outcome
        return {
            "id": "ADH-4", "title": "t", "description": "d", "status": status,
            "current_state": {"description": "d", "is_blocked": False},
            "history": [{"action": "item defined", "timestamp": "2026-07-01T00:00:00Z", "by": "x"}],
            "sessions": [entry],
        }

    def _structurally_empty(self, status="in progress"):
        return {
            "id": "ADH-9", "title": "t", "description": "d", "status": status,
            "current_state": {"description": "d", "is_blocked": False},
            "history": [
                {"action": "item defined", "timestamp": "2026-07-01T00:00:00Z", "by": "x"},
                {"action": "session started", "timestamp": "2026-07-01T00:05:00Z", "by": "x"},
            ],
            "sessions": [],
        }

    # -- open_episode: already-populated item (ADH-004 acceptance scenario) --

    def test_open_episode_appends_episode_2_to_populated_sessions(self):
        item = D.define_item(
            self._populated(), item_id="ADH-4", open_episode="ADH-4--e2", now=NOW)
        self.assertEqual(len(item["sessions"]), 2)
        first, second = item["sessions"]
        self.assertEqual(first["episode_number"], 1)
        self.assertEqual(first["closed"], "2026-08-01T00:00:00Z")
        self.assertEqual(second, {
            "episode_id": "ADH-4--e2", "episode_number": 2,
            "folder": "sessions/ADH-4--e2", "opened": NOW,
            "closed": None, "outcome": None,
        })

    def test_open_episode_sets_status_in_progress_and_records_history(self):
        item = D.define_item(
            self._populated(), item_id="ADH-4", open_episode="ADH-4--e2", now=NOW)
        self.assertEqual(item["status"], "in progress")
        self.assertEqual(item["history"][-1]["action"], "reopened as episode 2")
        self.assertEqual(item["history"][-1]["timestamp"], NOW)

    def test_open_episode_normalizes_missing_outcome_key_to_null_without_migration(self):
        # The 12 already-migrated live items have no `outcome` key at all.
        item = D.define_item(
            self._populated(outcome=None), item_id="ADH-4",
            open_episode="ADH-4--e2", now=NOW)
        self.assertIsNone(item["sessions"][0]["outcome"])

    def test_open_episode_refuses_when_last_episode_still_open(self):
        item_with_open_episode = self._populated(closed=None)
        with self.assertRaises(ValueError):
            D.define_item(
                item_with_open_episode, item_id="ADH-4",
                open_episode="ADH-4--e2", now=NOW)

    def test_open_episode_numbering_continues_past_two(self):
        existing = self._populated()
        existing["sessions"].append({
            "episode_id": "ADH-4--e2", "episode_number": 2,
            "folder": "sessions/ADH-4--e2", "opened": "2026-08-05T00:00:00Z",
            "closed": "2026-08-06T00:00:00Z", "outcome": "done",
        })
        item = D.define_item(existing, item_id="ADH-4", open_episode="ADH-4--e3", now=NOW)
        self.assertEqual(item["sessions"][-1]["episode_number"], 3)

    # -- open_episode: structurally-empty sessions[] (defensive branch, --
    # currently unreachable by any live item, per Gate A round 2) --

    def test_open_episode_backfills_episode_1_when_structurally_empty(self):
        item = D.define_item(
            self._structurally_empty(status="done"), item_id="ADH-9",
            open_episode="ADH-9--e2", now=NOW)
        self.assertEqual(len(item["sessions"]), 2)
        backfilled = item["sessions"][0]
        self.assertEqual(backfilled["episode_id"], "ADH-9")
        self.assertEqual(backfilled["episode_number"], 1)
        self.assertEqual(backfilled["folder"], "sessions/ADH-9")
        self.assertEqual(backfilled["opened"], "2026-07-01T00:00:00Z")
        self.assertEqual(backfilled["closed"], "2026-07-01T00:05:00Z")
        self.assertEqual(backfilled["outcome"], "done")
        self.assertEqual(item["sessions"][1]["episode_number"], 2)

    def test_open_episode_backfill_refuses_when_item_still_in_progress(self):
        # status "in progress" -> backfilled episode 1 has closed=None ->
        # last-episode-still-open guard correctly refuses.
        with self.assertRaises(ValueError):
            D.define_item(
                self._structurally_empty(status="in progress"), item_id="ADH-9",
                open_episode="ADH-9--e2", now=NOW)

    # -- close_episode: already-populated item, matching by episode_id
    # (IO-101 acceptance scenario) --

    def test_close_episode_closes_matching_entry_and_sets_status_done(self):
        item = D.define_item(
            self._populated(status="in progress", closed=None), item_id="ADH-4",
            close_episode=("ADH-4", "done"), now=NOW)
        self.assertEqual(item["sessions"][0]["closed"], NOW)
        self.assertEqual(item["sessions"][0]["outcome"], "done")
        self.assertEqual(item["status"], "done")

    def test_close_episode_with_non_done_outcome_leaves_status_untouched(self):
        item = D.define_item(
            self._populated(status="on hold", closed=None), item_id="ADH-4",
            close_episode=("ADH-4", "paused"), now=NOW)
        self.assertEqual(item["sessions"][0]["outcome"], "paused")
        self.assertEqual(item["status"], "on hold")

    def test_close_episode_records_history(self):
        item = D.define_item(
            self._populated(status="in progress", closed=None), item_id="ADH-4",
            close_episode=("ADH-4", "done"), event_by="end_work_session.prompt.md", now=NOW)
        self.assertEqual(item["history"][-1]["action"], "closed episode 1 (outcome: done)")
        self.assertEqual(item["history"][-1]["by"], "end_work_session.prompt.md")

    def test_close_episode_raises_when_no_matching_episode_id(self):
        with self.assertRaises(ValueError):
            D.define_item(
                self._populated(status="in progress", closed=None), item_id="ADH-4",
                close_episode=("ADH-4--e7", "done"), now=NOW)

    def test_close_episode_requires_outcome(self):
        with self.assertRaises(ValueError):
            D.define_item(
                self._populated(status="in progress", closed=None), item_id="ADH-4",
                close_episode=("ADH-4", ""), now=NOW)

    # -- close_episode: structurally-empty sessions[] (defensive branch —
    # closing episode 1 for an item that has never been reopened and
    # predates ADH-008's migration entirely, e.g. a fresh item created
    # after ADH-011 ships but before its first close) --

    def test_close_episode_backfills_and_closes_episode_1_when_structurally_empty(self):
        item = D.define_item(
            self._structurally_empty(status="in progress"), item_id="ADH-9",
            close_episode=("ADH-9", "done"), now=NOW)
        self.assertEqual(len(item["sessions"]), 1)
        self.assertEqual(item["sessions"][0]["episode_id"], "ADH-9")
        self.assertEqual(item["sessions"][0]["closed"], NOW)
        self.assertEqual(item["sessions"][0]["outcome"], "done")
        self.assertEqual(item["status"], "done")


class LegacyItemsWithoutSessionsField(unittest.TestCase):
    """Real existing items (pre-migration shape) have no `sessions` key."""

    def test_sessions_is_backfilled_as_empty_list_not_crash(self):
        legacy = {"id": "ADH-1", "title": "t", "description": "d", "status": "done",
                  "current_state": {"description": "d", "is_blocked": False}, "history": []}
        item = D.define_item(legacy, item_id="ADH-1", priority="Minor", now=NOW)
        self.assertEqual(item["sessions"], [])


if __name__ == "__main__":
    unittest.main()
