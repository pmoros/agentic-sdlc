"""Tests for task-based model selection (the model-routing gap).

Maps a worker's ROLE (or task type) to the right Claude model per the ADR-001
tiering: Opus for planning/reasoning, Sonnet for coding, Haiku for classify.
Before this, every worker defaulted to Sonnet 5 regardless of task.

Run: python3 autonomous-workflows/tests/test_routing.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import routing  # noqa: E402


class RoleModelTest(unittest.TestCase):
    def test_planner_is_opus(self):
        self.assertEqual(routing.model_for_role("planner"), "claude-opus-5")

    def test_architect_is_fable(self):
        self.assertEqual(routing.model_for_role("architect"), "claude-fable-5")

    def test_coder_is_sonnet(self):
        self.assertEqual(routing.model_for_role("coder"), "claude-sonnet-5")

    def test_classifier_is_haiku(self):
        self.assertEqual(routing.model_for_role("classifier"), "claude-haiku-4-5")

    def test_unknown_role_raises(self):
        with self.assertRaises(ValueError):
            routing.model_for_role("wizard")


class TaskTypeRoleTest(unittest.TestCase):
    def test_reasoning_task_types_map_to_planner(self):
        for tt in ("plan", "design", "review", "research", "spike"):
            self.assertEqual(routing.role_for_task_type(tt), "planner", tt)

    def test_escalation_task_types_map_to_architect(self):
        for tt in ("architect", "hard-debug", "deep-research"):
            self.assertEqual(routing.role_for_task_type(tt), "architect", tt)

    def test_coding_task_types_map_to_coder(self):
        for tt in ("code", "implement", "fix", "refactor", "feat", "test", "chore"):
            self.assertEqual(routing.role_for_task_type(tt), "coder", tt)

    def test_triage_task_types_map_to_classifier(self):
        for tt in ("classify", "triage", "route", "label"):
            self.assertEqual(routing.role_for_task_type(tt), "classifier", tt)

    def test_case_insensitive(self):
        self.assertEqual(routing.role_for_task_type("FIX"), "coder")

    def test_unknown_task_type_defaults_to_coder(self):
        self.assertEqual(routing.role_for_task_type("whatever"), "coder")


class SelectModelTest(unittest.TestCase):
    def test_by_role(self):
        self.assertEqual(routing.select_model(role="planner"), "claude-opus-5")
        self.assertEqual(routing.select_model(role="classifier"), "claude-haiku-4-5")

    def test_by_task_type(self):
        self.assertEqual(routing.select_model(task_type="design"), "claude-opus-5")
        self.assertEqual(routing.select_model(task_type="fix"), "claude-sonnet-5")

    def test_role_wins_over_task_type(self):
        self.assertEqual(routing.select_model(role="classifier", task_type="design"), "claude-haiku-4-5")

    def test_default_is_coder_sonnet(self):
        self.assertEqual(routing.select_model(), "claude-sonnet-5")


class LifecycleStageTaskTypesTest(unittest.TestCase):
    def test_discovery_and_planning_are_planner(self):
        for tt in ("discovery", "planning"):
            self.assertEqual(routing.role_for_task_type(tt), "planner", tt)

    def test_review_and_design_review_are_planner(self):
        for tt in ("review", "design-review"):
            self.assertEqual(routing.role_for_task_type(tt), "planner", tt)

    def test_qa_is_coder_sonnet(self):
        for tt in ("qa", "verify", "validate"):
            self.assertEqual(routing.role_for_task_type(tt), "coder", tt)


if __name__ == "__main__":
    unittest.main()
