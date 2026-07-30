"""Tests for the decomposition contract (fan-out build §3.2).

The planner's sub-tasks must be validated before plan_runs: schema, unique ids,
deps reference known ids and are acyclic, and NO two sub-tasks' touched_paths
overlap (two workers editing the same package = guaranteed conflict). Pure logic.

Run: python3 scripts/tests/test_decomposition.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ on path
import decomposition  # noqa: E402


def _st(tid, **kw):
    base = {"task_id": tid, "role": "coder", "goal": f"do {tid}"}
    base.update(kw)
    return base


class ValidateTest(unittest.TestCase):
    def test_valid_passes(self):
        subs = [_st("t1", touched_paths=["packages/a"]),
                _st("t2", task_type="fix", touched_paths=["packages/b"])]
        self.assertEqual(decomposition.validate_decomposition(subs), subs)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            decomposition.validate_decomposition([])

    def test_missing_task_id_raises(self):
        with self.assertRaises(ValueError):
            decomposition.validate_decomposition([{"role": "coder", "goal": "x"}])

    def test_duplicate_id_raises(self):
        with self.assertRaises(ValueError):
            decomposition.validate_decomposition([_st("t1"), _st("t1")])

    def test_missing_goal_raises(self):
        with self.assertRaises(ValueError):
            decomposition.validate_decomposition([{"task_id": "t1", "role": "coder"}])

    def test_missing_role_and_task_type_raises(self):
        with self.assertRaises(ValueError):
            decomposition.validate_decomposition([{"task_id": "t1", "goal": "x"}])

    def test_unknown_dep_raises(self):
        with self.assertRaises(ValueError):
            decomposition.validate_decomposition([_st("t1", deps=["tX"])])

    def test_cyclic_deps_raises(self):
        with self.assertRaises(ValueError):
            decomposition.validate_decomposition([_st("t1", deps=["t2"]), _st("t2", deps=["t1"])])

    def test_overlapping_touched_paths_raises(self):
        with self.assertRaises(ValueError):
            decomposition.validate_decomposition(
                [_st("t1", touched_paths=["packages/a"]),
                 _st("t2", touched_paths=["packages/a/sub"])])

    def test_disjoint_paths_ok(self):
        subs = [_st("t1", touched_paths=["packages/a"]), _st("t2", touched_paths=["packages/b"])]
        self.assertEqual(decomposition.validate_decomposition(subs), subs)


class PathOverlapTest(unittest.TestCase):
    def test_finds_overlap_pair(self):
        subs = [_st("t1", touched_paths=["src/x"]), _st("t2", touched_paths=["src/x/y"]),
                _st("t3", touched_paths=["docs"])]
        self.assertEqual(decomposition.find_path_overlaps(subs), [("t1", "t2")])

    def test_ancestor_overlap(self):
        self.assertTrue(decomposition._paths_overlap(["packages/a"], ["packages/a/x"]))

    def test_exact_overlap(self):
        self.assertTrue(decomposition._paths_overlap(["src/app.py"], ["src/app.py"]))

    def test_disjoint(self):
        self.assertFalse(decomposition._paths_overlap(["packages/a"], ["packages/b"]))

    def test_glob_normalized_overlap(self):
        self.assertTrue(decomposition._paths_overlap(["packages/a/**"], ["packages/a/x"]))


if __name__ == "__main__":
    unittest.main()
