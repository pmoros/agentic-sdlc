"""End-to-end tests for scripts/check-spec-complete.sh — locates a session's
SPEC.md and checks the `## Impact analysis` subsection is present with all
four fields non-empty.

Pure completeness-checking logic is covered in test_check_spec_complete.py;
this file covers only what a subprocess/filesystem test can — CLI parsing,
locating the session folder, and missing-file handling.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import script, make_work_sessions_repo, TempRepoCase  # noqa: E402

SCRIPT = script("check-spec-complete.sh")

COMPLETE_SPEC = """# Spec

## Impact analysis

- **Stakeholders:** who to notify or get approval from
- **Components:** services/repos/modules touched
- **Data dependencies:** schemas/datastores/queues read or written
- **Side effects:** anything outside the stated change surface (cost, other
  pipelines, shared infra)
"""

INCOMPLETE_SPEC = """# Spec

## Impact analysis

- **Stakeholders:**
- **Components:** services/repos/modules touched
- **Data dependencies:** schemas/datastores/queues read or written
- **Side effects:** anything outside the stated change surface
"""

NO_HEADING_SPEC = """# Spec

## Approach

No impact analysis section here at all.
"""


class CheckSpecComplete(TempRepoCase):
    def setUp(self):
        super().setUp()
        self.ws = make_work_sessions_repo(self.tmp)

    def write_spec(self, session_id, text):
        session_dir = os.path.join(self.ws, "sessions", session_id)
        os.makedirs(session_dir, exist_ok=True)
        with open(os.path.join(session_dir, "SPEC.md"), "w") as fh:
            fh.write(text)

    def check(self, session_id, extra=()):
        return subprocess.run(
            [SCRIPT, session_id, "--work-sessions-repo", self.ws, *extra],
            capture_output=True, text=True,
        )

    # --- happy path ---------------------------------------------------

    def test_complete_impact_analysis_passes(self):
        self.write_spec("ADH-9", COMPLETE_SPEC)
        r = self.check("ADH-9")
        self.assertEqual(r.returncode, 0, r.stderr)

    # --- failures -------------------------------------------------------

    def test_empty_field_fails_and_lists_it(self):
        self.write_spec("ADH-9", INCOMPLETE_SPEC)
        r = self.check("ADH-9")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Stakeholders", r.stderr)

    def test_missing_heading_fails_and_lists_all_four_fields(self):
        self.write_spec("ADH-9", NO_HEADING_SPEC)
        r = self.check("ADH-9")
        self.assertNotEqual(r.returncode, 0)
        for field in ("Stakeholders", "Components", "Data dependencies", "Side effects"):
            self.assertIn(field, r.stderr)

    def test_missing_spec_file_fails(self):
        os.makedirs(os.path.join(self.ws, "sessions", "ADH-9"), exist_ok=True)
        r = self.check("ADH-9")
        self.assertNotEqual(r.returncode, 0)

    # --- argument validation -------------------------------------------

    def test_requires_session_id(self):
        r = subprocess.run([SCRIPT, "--work-sessions-repo", self.ws],
                            capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_rejects_unknown_flag(self):
        self.write_spec("ADH-9", COMPLETE_SPEC)
        r = self.check("ADH-9", ["--not-a-real-flag"])
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
