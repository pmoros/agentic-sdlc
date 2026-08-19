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


class LegacyItemsWithoutSessionsField(unittest.TestCase):
    """Real existing items (pre-migration shape) have no `sessions` key."""

    def test_sessions_is_backfilled_as_empty_list_not_crash(self):
        legacy = {"id": "ADH-1", "title": "t", "description": "d", "status": "done",
                  "current_state": {"description": "d", "is_blocked": False}, "history": []}
        item = D.define_item(legacy, item_id="ADH-1", priority="Minor", now=NOW)
        self.assertEqual(item["sessions"], [])


if __name__ == "__main__":
    unittest.main()
