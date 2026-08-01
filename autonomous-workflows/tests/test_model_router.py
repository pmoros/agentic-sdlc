"""Tests for window-/strength-aware model selection (ADH-005 D4).

`choose_model(spec, window)` is pure: strength-map base + per-family window
headroom -> {model, reason, action}. Proves the fail-closed invariant
(upgrade-or-defer, never downgrade; Fable never auto-reached; ladder is
Sonnet->Opus only). No I/O.

Run: python3 autonomous-workflows/tests/test_model_router.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import model_router  # noqa: E402


def _win(**fams):
    """Build a per-family window summary; unspecified families are clear."""
    base = {f: {"headroom": 5.0, "tight": False} for f in ("opus", "sonnet", "haiku", "fable")}
    for f, tight in fams.items():
        base[f] = {"headroom": (0.5 if tight else 5.0), "tight": tight}
    return base


def _spec(model, task_type="code"):
    return {"model": model, "task_type": task_type}


class ChooseModelTest(unittest.TestCase):
    def test_all_clear_returns_strength_map(self):
        r = model_router.choose_model(_spec("claude-sonnet-5"), _win())
        self.assertEqual((r["model"], r["action"]), ("claude-sonnet-5", "route"))

    def test_no_window_returns_base(self):
        r = model_router.choose_model(_spec("claude-sonnet-5"), None)
        self.assertEqual((r["model"], r["action"]), ("claude-sonnet-5", "route"))

    def test_sonnet_tight_eligible_opus_clear_upgrades(self):
        r = model_router.choose_model(_spec("claude-sonnet-5", "fix"), _win(sonnet=True))
        self.assertEqual(r["model"], "claude-opus-5")
        self.assertEqual(r["action"], "route")
        self.assertEqual(r["reason"], "sonnet_tight_upgraded_to_opus")

    def test_sonnet_tight_eligible_but_opus_also_tight_defers(self):
        r = model_router.choose_model(_spec("claude-sonnet-5", "fix"), _win(sonnet=True, opus=True))
        self.assertEqual(r["action"], "defer_window")
        self.assertEqual(r["model"], "claude-sonnet-5")   # never downgraded

    def test_sonnet_tight_not_eligible_stays_sonnet(self):
        # a non-upgrade-eligible task type stays on Sonnet (no silent downgrade, no defer)
        r = model_router.choose_model(_spec("claude-sonnet-5", "summarize"), _win(sonnet=True))
        self.assertEqual((r["model"], r["action"]), ("claude-sonnet-5", "route"))
        self.assertEqual(r["reason"], "sonnet_tight_not_eligible")

    def test_opus_base_returns_opus_even_when_tight(self):
        # nothing above Opus in the rebalancer; admission is can_start's job
        r = model_router.choose_model(_spec("claude-opus-5", "design"), _win(opus=True))
        self.assertEqual((r["model"], r["action"]), ("claude-opus-5", "route"))

    def test_haiku_base_returns_haiku(self):
        r = model_router.choose_model(_spec("claude-haiku-4-5", "triage"), _win(haiku=True))
        self.assertEqual((r["model"], r["action"]), ("claude-haiku-4-5", "route"))

    def test_fable_base_clear_routes(self):
        r = model_router.choose_model(_spec("claude-fable-5", "architect"), _win())
        self.assertEqual((r["model"], r["action"]), ("claude-fable-5", "route"))

    def test_fable_base_ceiling_hit_defers_not_downgrades(self):
        r = model_router.choose_model(_spec("claude-fable-5", "architect"), _win(fable=True))
        self.assertEqual(r["action"], "defer_window")
        self.assertEqual(r["model"], "claude-fable-5")   # never downgraded to opus

    def test_never_reaches_fable_by_escalation(self):
        # a Sonnet task under pressure can only reach Opus, never Fable
        r = model_router.choose_model(_spec("claude-sonnet-5", "fix"), _win(sonnet=True))
        self.assertNotEqual(r["model"], "claude-fable-5")


if __name__ == "__main__":
    unittest.main()
