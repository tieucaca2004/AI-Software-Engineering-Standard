"""Budget evaluator tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from token_efficiency import evaluator as E  # noqa: E402


def pol(**over):
    r = {"schema": "ases-budget-policy/1", "policy_id": "p1", "policy_version": "1",
         "scope": "work-unit", "metric": "tokens",
         "warning_threshold": 100000, "block_threshold": 200000}
    r.update(over)
    return r


def usage(**over):
    r = {"scope": "work-unit", "work_unit_id": "wu-1", "completeness": "complete",
         "total_tokens": 50000, "total_cost_usd": 1.0, "evidence_refs": ["u1.json"]}
    r.update(over)
    return r


class EvaluatorTests(unittest.TestCase):
    def test_below_warning_allow(self):
        d = E.evaluate(pol(), usage(total_tokens=50000), policy_ref="p1.json")
        self.assertEqual(d["decision"], "ALLOW")
        self.assertTrue(d["admits_next"])

    def test_at_warning_warn(self):
        d = E.evaluate(pol(), usage(total_tokens=100000), policy_ref="p1.json")
        self.assertEqual(d["decision"], "WARN")
        self.assertTrue(d["admits_next"])

    def test_between_warn(self):
        d = E.evaluate(pol(), usage(total_tokens=150000), policy_ref="p1.json")
        self.assertEqual(d["decision"], "WARN")

    def test_at_block_block(self):
        d = E.evaluate(pol(), usage(total_tokens=200000), policy_ref="p1.json")
        self.assertEqual(d["decision"], "BLOCK")
        self.assertFalse(d["admits_next"])

    def test_above_block_block(self):
        d = E.evaluate(pol(), usage(total_tokens=999999), policy_ref="p1.json")
        self.assertEqual(d["decision"], "BLOCK")

    def test_missing_usage_unavailable(self):
        d = E.evaluate(pol(), None, policy_ref="p1.json")
        self.assertEqual(d["decision"], "UNAVAILABLE")

    def test_partial_usage_unavailable(self):
        d = E.evaluate(pol(), usage(completeness="partial"), policy_ref="p1.json")
        self.assertEqual(d["decision"], "UNAVAILABLE")
        self.assertFalse(d["admits_next"])

    def test_invalid_usage_unavailable(self):
        d = E.evaluate(pol(), {"scope": "work-unit"}, policy_ref="p1.json")
        self.assertEqual(d["decision"], "UNAVAILABLE")

    def test_invalid_policy_unavailable_not_allow(self):
        d = E.evaluate({"metric": "tokens"}, usage(), policy_ref="p1.json")
        self.assertEqual(d["decision"], "UNAVAILABLE")
        self.assertFalse(d["admits_next"])

    def test_null_metric_value_unavailable(self):
        d = E.evaluate(pol(), usage(total_tokens=None), policy_ref="p1.json")
        self.assertEqual(d["decision"], "UNAVAILABLE")

    def test_cost_metric(self):
        p = pol(metric="cost", warning_threshold=1.0, block_threshold=2.0)
        d = E.evaluate(p, usage(total_cost_usd=1.5, total_tokens=None), policy_ref="p1.json")
        self.assertEqual(d["decision"], "WARN")
        self.assertEqual(d["measured_value"], 1.5)

    def test_deterministic(self):
        a = E.evaluate(pol(), usage(total_tokens=150000), policy_ref="p1.json")
        b = E.evaluate(pol(), usage(total_tokens=150000), policy_ref="p1.json")
        self.assertEqual(a["decision"], b["decision"])


if __name__ == "__main__":
    unittest.main()
