"""ases-budget-decision/1 validation tests."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from token_efficiency import decision as D  # noqa: E402


def dec(**over):
    r = {"schema": D.DECISION_SCHEMA, "decision_id": "d1", "evaluated_utc": "2026-11-22T14:00:00Z",
         "scope": "work-unit", "work_unit_id": "wu-1", "decision": "ALLOW", "reason": "ok",
         "policy_ref": "policy.json", "policy_version": "1", "metric": "tokens",
         "measured_value": 50000, "warning_threshold": 100000, "block_threshold": 200000,
         "usage_refs": ["u1.json"], "admits_next": True, "override": None}
    r.update(over)
    return r


class DecisionTests(unittest.TestCase):
    def test_valid(self):
        D.validate_decision(dec())

    def test_invalid_schema(self):
        with self.assertRaises(D.DecisionError):
            D.validate_decision(dec(schema="ases-budget-decision/9"))

    def test_invalid_decision_enum(self):
        with self.assertRaises(D.DecisionError):
            D.validate_decision(dec(decision="MAYBE"))

    def test_correct_refs(self):
        d = dec(policy_ref="p.json", policy_version="2", usage_refs=["a.json", "b.json"])
        D.validate_decision(d)
        self.assertEqual(d["policy_ref"], "p.json")

    def test_attribution(self):
        d = dec(work_unit_id="wu-42", scope="work-unit")
        D.validate_decision(d)
        self.assertEqual(d["work_unit_id"], "wu-42")

    def test_block_requires_override_to_admit(self):
        with self.assertRaises(D.DecisionError):
            D.validate_decision(dec(decision="BLOCK", admits_next=True, override=None))

    def test_block_with_override_admits(self):
        d = dec(decision="BLOCK", admits_next=True,
                override={"authorized_by": "founder", "scope": "wu-1", "ref": "override.json"})
        D.validate_decision(d)

    def test_unavailable_no_admit_without_override(self):
        with self.assertRaises(D.DecisionError):
            D.validate_decision(dec(decision="UNAVAILABLE", admits_next=True))

    def test_evidence_retrievable_after_persist(self):
        d = dec()
        fd, path = tempfile.mkstemp(prefix="budget-decision-", suffix=".json")
        os.close(fd)
        with open(path, "w") as f:
            json.dump(d, f)
        with open(path) as f:
            loaded = json.load(f)
        D.validate_decision(loaded)
        os.remove(path)

    def test_negative_measured_value(self):
        with self.assertRaises(D.DecisionError):
            D.validate_decision(dec(measured_value=-1))


if __name__ == "__main__":
    unittest.main()
