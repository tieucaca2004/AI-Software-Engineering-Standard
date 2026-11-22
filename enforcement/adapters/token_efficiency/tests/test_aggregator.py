"""Usage aggregation and conflict-handling tests."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from token_efficiency import aggregator as A  # noqa: E402
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


def recs(*items):
    """Convert a list of (record, ref) or record into (record, ref) pairs."""
    out = []
    for it in items:
        if isinstance(it, tuple):
            out.append(it)
        else:
            out.append((it, "ref-" + it.get("request_id", "x")))
    return out


SCOPE = {"scope": "work-unit", "work_unit_id": "wu-1"}


class DedupTests(unittest.TestCase):
    def test_identical_complete_dedup(self):
        snap = A.aggregate(recs(usage(), usage()), SCOPE)
        self.assertEqual(snap["complete_totals"]["request_count"], 1)
        self.assertEqual(snap["completeness_status"], "complete")

    def test_partial_then_complete_replacement(self):
        snap = A.aggregate(recs(usage(completeness="partial", output_tokens=None),
                                usage()), SCOPE)
        self.assertEqual(snap["complete_totals"]["request_count"], 1)
        self.assertEqual(snap["completeness_status"], "complete")
        self.assertEqual(snap["complete_totals"]["total_tokens"], 10)

    def test_same_request_once(self):
        snap = A.aggregate(recs(usage(), usage(), usage(completeness="partial", output_tokens=None)), SCOPE)
        self.assertEqual(snap["complete_totals"]["request_count"], 1)

    def test_different_requests_separate(self):
        snap = A.aggregate(recs(usage(request_id="r1"), usage(request_id="r2")), SCOPE)
        self.assertEqual(snap["complete_totals"]["request_count"], 2)
        self.assertEqual(snap["complete_totals"]["total_tokens"], 20)


class ConflictTests(unittest.TestCase):
    def test_conflicting_complete(self):
        snap = A.aggregate(recs(usage(input_tokens=1), usage(input_tokens=99)), SCOPE)
        self.assertEqual(snap["completeness_status"], "conflicted")
        self.assertEqual(len(snap["conflicts"]), 1)
        self.assertIn("input_tokens", snap["conflicts"][0]["differing_fields"])
        self.assertEqual(snap["complete_totals"]["request_count"], 0)  # excluded from primary

    def test_conflict_excluded_from_primary(self):
        snap = A.aggregate(recs(usage(request_id="r1", input_tokens=1),
                                usage(request_id="r1", input_tokens=2),
                                usage(request_id="r2")), SCOPE)
        self.assertEqual(snap["complete_totals"]["request_count"], 1)  # only r2 counted
        self.assertEqual(snap["complete_totals"]["total_tokens"], 10)

    def test_no_first_last_resolution(self):
        snap = A.aggregate(recs(usage(input_tokens=1), usage(input_tokens=2), usage(input_tokens=3)), SCOPE)
        self.assertEqual(snap["completeness_status"], "conflicted")
        self.assertEqual(len(snap["conflicts"]), 1)


class TotalsTests(unittest.TestCase):
    def test_token_formulas(self):
        # input=1, output=2, cache_create=3, cache_read=4 -> input total=8, output=2, total=10
        snap = A.aggregate(recs(usage()), SCOPE)
        ct = snap["complete_totals"]
        self.assertEqual(ct["total_input_tokens"], 8)
        self.assertEqual(ct["total_output_tokens"], 2)
        self.assertEqual(ct["total_tokens"], 10)

    def test_no_thinking_double_count(self):
        snap = A.aggregate(recs(usage(thinking_tokens=1000)), SCOPE)
        self.assertEqual(snap["complete_totals"]["total_tokens"], 10)  # thinking not added

    def test_no_cache_double_count(self):
        snap = A.aggregate(recs(usage(cache_creation_input_tokens=3, cache_read_input_tokens=4)), SCOPE)
        self.assertEqual(snap["complete_totals"]["total_input_tokens"], 8)  # 1+3+4, not doubled

    def test_cost_sum(self):
        snap = A.aggregate(recs(usage(request_id="r1", total_cost_usd=0.5),
                                usage(request_id="r2", total_cost_usd=0.25)), SCOPE)
        self.assertAlmostEqual(snap["complete_totals"]["total_cost_usd"], 0.75)

    def test_missing_cost_stays_null(self):
        snap = A.aggregate(recs(usage(total_cost_usd=None)), SCOPE)
        self.assertIsNone(snap["complete_totals"]["total_cost_usd"])


class BudgetSafetyTests(unittest.TestCase):
    def test_complete_scope_complete_m3_input(self):
        snap = A.aggregate(recs(usage()), SCOPE)
        self.assertEqual(snap["m3_input"]["completeness"], "complete")
        self.assertEqual(snap["m3_input"]["total_tokens"], 10)

    def test_partial_scope_not_complete(self):
        snap = A.aggregate(recs(usage(request_id="r1"),
                                usage(request_id="r2", completeness="partial", output_tokens=None)), SCOPE)
        self.assertNotEqual(snap["m3_input"]["completeness"], "complete")
        self.assertIsNone(snap["m3_input"]["total_tokens"])

    def test_conflicted_scope_not_complete(self):
        snap = A.aggregate(recs(usage(input_tokens=1), usage(input_tokens=2)), SCOPE)
        self.assertNotEqual(snap["m3_input"]["completeness"], "complete")
        self.assertIsNone(snap["m3_input"]["total_tokens"])

    def test_unavailable_scope(self):
        snap = A.aggregate(recs(usage(completeness="unavailable", source="unavailable",
                                      input_tokens=None, output_tokens=None,
                                      cache_creation_input_tokens=None, cache_read_input_tokens=None)), SCOPE)
        self.assertEqual(snap["completeness_status"], "partial")
        self.assertIsNone(snap["m3_input"]["total_tokens"])

    def test_empty_inventory(self):
        snap = A.aggregate([], SCOPE)
        self.assertEqual(snap["completeness_status"], "unavailable")
        self.assertIsNone(snap["m3_input"]["total_tokens"])


class EvidenceDeterminismTests(unittest.TestCase):
    def test_invalid_record_preserved(self):
        snap = A.aggregate(recs(usage(), {"schema": "ases-usage/1"}), SCOPE)
        self.assertEqual(len(snap["invalid_inputs"]), 1)

    def test_snapshot_validates(self):
        snap = A.aggregate(recs(usage()), SCOPE)
        S.validate_snapshot(snap)

    def test_deterministic_totals(self):
        a = A.aggregate(recs(usage(), usage(request_id="r2")), SCOPE)
        b = A.aggregate(recs(usage(), usage(request_id="r2")), SCOPE)
        self.assertEqual(a["complete_totals"], b["complete_totals"])

    def test_source_not_modified(self):
        r = usage()
        before = json.dumps(r, sort_keys=True)
        A.aggregate(recs(r), SCOPE)
        self.assertEqual(json.dumps(r, sort_keys=True), before)

    def test_persist_retrievable(self):
        snap = A.aggregate(recs(usage()), SCOPE)
        fd, path = tempfile.mkstemp(prefix="agg-", suffix=".json")
        os.close(fd)
        A.persist_snapshot(snap, path)
        with open(path) as f:
            loaded = json.load(f)
        self.assertEqual(loaded["complete_totals"]["total_tokens"], 10)
        os.remove(path)

    def test_m3_feed(self):
        from token_efficiency import evaluator as E
        snap = A.aggregate(recs(usage()), SCOPE)
        policy = {"schema": "ases-budget-policy/1", "policy_id": "p1", "policy_version": "1",
                  "scope": "work-unit", "metric": "tokens",
                  "warning_threshold": 100, "block_threshold": 1000}
        d = E.evaluate(policy, snap["m3_input"], policy_ref="p.json")
        self.assertEqual(d["decision"], "ALLOW")

    def test_cli_end_to_end(self):
        from token_efficiency import agg_cli
        d = tempfile.mkdtemp(prefix="m4-cli-")
        u1 = os.path.join(d, "u1.json")
        u2 = os.path.join(d, "u2.json")
        with open(u1, "w") as f:
            json.dump(usage(request_id="r1"), f)
        with open(u2, "w") as f:
            json.dump(usage(request_id="r2"), f)
        snap_path = os.path.join(d, "snapshot.json")
        m3_path = os.path.join(d, "m3.json")
        agg_cli.main(["--usage-files", u1, u2, "--scope", "work-unit", "--work-unit-id", "wu-1",
                      "--output", snap_path, "--m3-output", m3_path])
        with open(snap_path) as f:
            snap = json.load(f)
        S.validate_snapshot(snap)
        self.assertEqual(snap["complete_totals"]["total_tokens"], 20)
        with open(m3_path) as f:
            m3 = json.load(f)
        self.assertEqual(m3["completeness"], "complete")


if __name__ == "__main__":
    unittest.main()
