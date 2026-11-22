"""M5 end-to-end integration tests: usage -> aggregate -> evaluate -> decision -> admission."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from token_efficiency import aggregator as A  # noqa: E402
from token_efficiency import decision as D  # noqa: E402
from token_efficiency import evaluator as E  # noqa: E402
from token_efficiency import evidence  # noqa: E402
from token_efficiency import snapshot as S  # noqa: E402


def usage(request_id="r1", work_unit_id="wu-1", completeness="complete", **over):
    r = {"schema": "ases-usage/1", "request_id": request_id, "work_unit_id": work_unit_id,
         "provider_id": "claude-cli", "source": "provider-reported", "completeness": completeness,
         "input_tokens": 1, "output_tokens": 2,
         "cache_creation_input_tokens": 3, "cache_read_input_tokens": 4,
         "thinking_tokens": 0, "total_cost_usd": 0.5,
         "captured_utc": "2026-11-22T14:00:00Z", "raw_ref": None}
    r.update(over)
    return r


SCOPE = {"scope": "work-unit", "work_unit_id": "wu-1"}
POLICY = {"schema": "ases-budget-policy/1", "policy_id": "p1", "policy_version": "1",
          "scope": "work-unit", "metric": "tokens",
          "warning_threshold": 50, "block_threshold": 100}


def run_workflow(records, policy=POLICY, scope=SCOPE, policy_ref="policy.json", evidence_dir=None):
    """Full workflow: persist usage -> aggregate -> evaluate -> persist decision."""
    evidence_dir = evidence_dir or tempfile.mkdtemp(prefix="m5-e2e-")
    # 1. persist usage records durably
    persisted = []
    for rec in records:
        ref = evidence.persist_json(rec, evidence_dir=evidence_dir, kind="usage",
                                    name=rec.get("request_id"))
        persisted.append((rec, ref))
    # 2. aggregate
    snap = A.aggregate(persisted, scope)
    snap_ref = A.persist_snapshot(snap, evidence_dir=evidence_dir)
    # 3. evaluate
    decision = E.evaluate(policy, snap["m3_input"], policy_ref=policy_ref)
    D.validate_decision(decision)
    decision_ref = evidence.persist_json(decision, evidence_dir=evidence_dir, kind="decision")
    return {"records": persisted, "snapshot": snap, "snapshot_ref": snap_ref,
            "decision": decision, "decision_ref": decision_ref}


class EndToEndTests(unittest.TestCase):
    def test_complete_allow_and_traceable(self):
        r = run_workflow([usage(request_id="r1"), usage(request_id="r2")])
        self.assertEqual(r["decision"]["decision"], "ALLOW")
        self.assertTrue(r["decision"]["admits_next"])
        # traceability: decision references policy + usage evidence
        self.assertEqual(r["decision"]["policy_ref"], "policy.json")
        self.assertGreaterEqual(len(r["decision"]["usage_refs"]), 1)
        # decision evidence retrievable + valid
        loaded = evidence.load_json(r["decision_ref"], D.validate_decision)
        self.assertEqual(loaded["decision"], "ALLOW")

    def test_over_budget_block(self):
        r = run_workflow([usage(request_id="r1", input_tokens=1000)], POLICY)
        self.assertEqual(r["decision"]["decision"], "BLOCK")
        self.assertFalse(r["decision"]["admits_next"])

    def test_partial_unavailable(self):
        rec = usage(request_id="r1", completeness="partial", output_tokens=None)
        r = run_workflow([rec])
        self.assertEqual(r["decision"]["decision"], "UNAVAILABLE")
        self.assertFalse(r["decision"]["admits_next"])

    def test_conflict_no_false_allow(self):
        r = run_workflow([usage(request_id="r1", input_tokens=1),
                          usage(request_id="r1", input_tokens=2)])
        self.assertIn(r["decision"]["decision"], ("UNAVAILABLE", "BLOCK"))
        self.assertFalse(r["decision"]["admits_next"])

    def test_missing_evidence_no_false_allow(self):
        r = run_workflow([])
        self.assertEqual(r["decision"]["decision"], "UNAVAILABLE")

    def test_snapshot_valid_and_attributed(self):
        r = run_workflow([usage(request_id="r1", work_unit_id="wu-1")])
        S.validate_snapshot(r["snapshot"])
        self.assertIn("wu-1", r["snapshot"]["work_unit_ids"])
        self.assertEqual(r["snapshot"]["complete_totals"]["total_tokens"], 10)

    def test_no_double_count(self):
        # thinking + cache breakdowns must not double-count
        r = run_workflow([usage(request_id="r1", thinking_tokens=1000,
                                cache_creation_input_tokens=3, cache_read_input_tokens=4)])
        self.assertEqual(r["snapshot"]["complete_totals"]["total_tokens"], 10)

    def test_workflow_uses_real_provider_normalization(self):
        # Verify M2's normalize_usage output is a valid aggregator input.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "claude-cli"))
        import claude_adapter as m2
        adapter = m2.ClaudeCliAdapter({})
        provider_json = json.dumps({
            "total_cost_usd": 0.5,
            "usage": {"input_tokens": 1, "output_tokens": 2,
                      "cache_creation_input_tokens": 3, "cache_read_input_tokens": 4,
                      "output_tokens_details": {"thinking_tokens": 0}},
        })
        rec = adapter.normalize_usage({"request_id": "r1", "work_unit_id": "wu-1"}, provider_json)
        snap = A.aggregate([(rec, None)], SCOPE)
        self.assertEqual(snap["complete_totals"]["total_tokens"], 10)


if __name__ == "__main__":
    unittest.main()
