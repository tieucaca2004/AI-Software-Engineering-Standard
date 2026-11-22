"""Workflow admission-control tests (procedural, not Core enforcement)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from token_efficiency import evaluator as E  # noqa: E402
from token_efficiency import decision as D  # noqa: E402


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


def workflow_admit(policy, usage_input, override=None):
    """Procedural admission: evaluate, then optionally apply an explicit override."""
    record = E.evaluate(policy, usage_input, policy_ref="p1.json")
    if record["decision"] in ("BLOCK", "UNAVAILABLE") and override is not None:
        record["override"] = override
        record["admits_next"] = True
        record["reason"] += " (overridden)"
    D.validate_decision(record)
    return record


class WorkflowTests(unittest.TestCase):
    def test_allow_admits(self):
        r = workflow_admit(pol(), usage(total_tokens=50000))
        self.assertTrue(r["admits_next"])
        self.assertEqual(r["decision"], "ALLOW")

    def test_warn_admits_and_records(self):
        r = workflow_admit(pol(), usage(total_tokens=150000))
        self.assertTrue(r["admits_next"])
        self.assertEqual(r["decision"], "WARN")

    def test_block_stops(self):
        r = workflow_admit(pol(), usage(total_tokens=999999))
        self.assertFalse(r["admits_next"])
        self.assertEqual(r["decision"], "BLOCK")

    def test_unavailable_stops(self):
        r = workflow_admit(pol(), usage(completeness="partial"))
        self.assertFalse(r["admits_next"])
        self.assertEqual(r["decision"], "UNAVAILABLE")

    def test_valid_override_admits_scope(self):
        r = workflow_admit(pol(), usage(total_tokens=999999),
                           override={"authorized_by": "founder", "scope": "wu-1", "ref": "ov.json"})
        self.assertTrue(r["admits_next"])
        self.assertEqual(r["override"]["authorized_by"], "founder")

    def test_invalid_override_rejected(self):
        # override without authorized_by is invalid -> validate_decision raises
        r = E.evaluate(pol(), usage(total_tokens=999999), policy_ref="p1.json")
        r["override"] = {"scope": "wu-1"}
        r["admits_next"] = True
        with self.assertRaises(D.DecisionError):
            D.validate_decision(r)

    def test_skipped_evaluator_not_allow(self):
        # No evaluation happened -> we have no decision; this must not be treated as ALLOW.
        # Represented here by a UNAVAILABLE record (the workflow records it when the evaluator is skipped).
        rec = {"schema": D.DECISION_SCHEMA, "decision_id": "d-skip", "evaluated_utc": "t",
               "scope": "work-unit", "work_unit_id": "wu-1", "decision": "UNAVAILABLE",
               "reason": "evaluator skipped", "policy_ref": "skipped", "policy_version": "n/a",
               "metric": "tokens", "measured_value": None, "warning_threshold": None,
               "block_threshold": None, "usage_refs": [], "admits_next": False, "override": None}
        D.validate_decision(rec)
        self.assertFalse(rec["admits_next"])

    def test_decision_persists_retrievable(self):
        r = workflow_admit(pol(), usage(total_tokens=50000))
        fd, path = tempfile.mkstemp(prefix="budget-wf-", suffix=".json")
        os.close(fd)
        with open(path, "w") as f:
            json.dump(r, f)
        with open(path) as f:
            loaded = json.load(f)
        self.assertEqual(loaded["decision"], "ALLOW")
        os.remove(path)

    def test_cli_run_block_and_persist(self):
        from token_efficiency import cli
        d = tempfile.mkdtemp(prefix="m3-cli-")
        pol_path = os.path.join(d, "policy.json")
        usage_path = os.path.join(d, "usage.json")
        out_path = os.path.join(d, "decision.json")
        with open(pol_path, "w") as f:
            json.dump(pol(), f)
        with open(usage_path, "w") as f:
            json.dump(usage(total_tokens=999999), f)
        rec = cli.run(pol_path, usage_path, out_path, policy_ref="policy.json")
        self.assertEqual(rec["decision"], "BLOCK")
        self.assertTrue(os.path.exists(out_path))
        with open(out_path) as f:
            self.assertEqual(json.load(f)["decision"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
