"""Evidence persistence and independent-process retrieval tests (M4 closure)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from token_efficiency import evidence  # noqa: E402
from token_efficiency import aggregator as A  # noqa: E402
from token_efficiency import snapshot as S  # noqa: E402
from agent_provider_contract import validation as uv  # noqa: E402

ADAPTERS_DIR = str(Path(__file__).resolve().parents[2])


def usage(request_id="r1", work_unit_id="wu-1", **over):
    r = {"schema": "ases-usage/1", "request_id": request_id, "work_unit_id": work_unit_id,
         "provider_id": "claude-cli", "source": "provider-reported", "completeness": "complete",
         "input_tokens": 1, "output_tokens": 2,
         "cache_creation_input_tokens": 3, "cache_read_input_tokens": 4,
         "thinking_tokens": 0, "total_cost_usd": 0.5,
         "captured_utc": "2026-11-22T14:00:00Z", "raw_ref": None}
    r.update(over)
    return r


SCOPE = {"scope": "work-unit", "work_unit_id": "wu-1"}


class PersistenceTests(unittest.TestCase):
    def test_default_evidence_dir_not_temp(self):
        d = evidence.default_evidence_dir()
        self.assertNotIn("Temp", d)
        self.assertIn(".ases", d)

    def test_durable_snapshot_creation(self):
        d = tempfile.mkdtemp(prefix="ev-")
        snap = A.aggregate([(usage(request_id="r1"), None)], SCOPE)
        ref = A.persist_snapshot(snap, evidence_dir=d)
        self.assertTrue(os.path.exists(ref))
        self.assertTrue(os.path.exists(ref + ".sha256"))

    def test_durable_m3_input_creation(self):
        d = tempfile.mkdtemp(prefix="ev-")
        snap = A.aggregate([(usage(), None)], SCOPE)
        ref = evidence.persist_json(snap["m3_input"], evidence_dir=d, kind="m3-input")
        self.assertTrue(os.path.exists(ref))

    def test_hash_verification_corrupt(self):
        d = tempfile.mkdtemp(prefix="ev-")
        ref = evidence.persist_json(usage(), evidence_dir=d, kind="usage", name="r1")
        with open(ref, "a") as f:
            f.write("tampered")
        with self.assertRaises(ValueError):
            evidence.load_json(ref, uv.validate_usage)

    def test_missing_evidence(self):
        with self.assertRaises(FileNotFoundError):
            evidence.load_json(os.path.join(tempfile.mkdtemp(), "nope.json"))

    def test_unreadable_evidence(self):
        d = tempfile.mkdtemp(prefix="ev-")
        ref = os.path.join(d, "bad.json")
        with open(ref, "w") as f:
            f.write("not json")
        with open(ref + ".sha256", "w") as f:
            f.write("x")
        with self.assertRaises(Exception):
            evidence.load_json(ref)

    def test_write_failure_surfaced(self):
        d = tempfile.mkdtemp(prefix="ev-")
        # a file at the kind-dir path forces os.makedirs to fail (FileExistsError)
        with open(os.path.join(d, "usage2"), "w") as f:
            f.write("x")
        with self.assertRaises(OSError):
            evidence.persist_json(usage(), evidence_dir=d, kind="usage2", name="r1")

    def test_source_not_modified(self):
        r = usage()
        before = json.dumps(r, sort_keys=True)
        d = tempfile.mkdtemp(prefix="ev-")
        evidence.persist_json(r, evidence_dir=d, kind="usage", name="r1")
        self.assertEqual(json.dumps(r, sort_keys=True), before)

    def test_no_false_complete_from_missing(self):
        # a missing usage file must not produce a complete snapshot
        snap = A.aggregate([], SCOPE)
        self.assertNotEqual(snap["m3_input"]["completeness"], "complete")
        self.assertIsNone(snap["m3_input"]["total_tokens"])


class IndependentProcessTests(unittest.TestCase):
    def test_two_process_retrieval(self):
        evidence_dir = tempfile.mkdtemp(prefix="ases-evidence-")

        # ---- Process A: create + persist durable evidence, then return (test process) ----
        u1 = usage(request_id="r1")
        u2 = usage(request_id="r2")
        u1_ref = evidence.persist_json(u1, evidence_dir=evidence_dir, kind="usage", name="r1")
        u2_ref = evidence.persist_json(u2, evidence_dir=evidence_dir, kind="usage", name="r2")
        snap = A.aggregate([(u1, u1_ref), (u2, u2_ref)], SCOPE)
        snap_ref = A.persist_snapshot(snap, evidence_dir=evidence_dir)
        m3_ref = evidence.persist_json(snap["m3_input"], evidence_dir=evidence_dir, kind="m3-input")

        refs = {"usage_refs": [u1_ref, u2_ref], "snapshot_ref": snap_ref, "m3_ref": m3_ref}
        refs_file = os.path.join(evidence_dir, "refs.json")
        with open(refs_file, "w") as f:
            json.dump(refs, f)

        # ---- Process B: independent OS process retrieves using only the references ----
        script = (
            "import json, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from token_efficiency import evidence\n"
            "from token_efficiency import snapshot as S\n"
            "from agent_provider_contract import validation as uv\n"
            "refs = json.load(open(sys.argv[2], encoding='utf-8'))\n"
            "for ref in refs['usage_refs']:\n"
            "    rec = evidence.load_json(ref, uv.validate_usage)\n"
            "    assert rec['request_id'] in ('r1', 'r2')\n"
            "snap = evidence.load_json(refs['snapshot_ref'], S.validate_snapshot)\n"
            "assert snap['complete_totals']['total_tokens'] == 20\n"
            "m3 = evidence.load_json(refs['m3_ref'])\n"
            "assert m3['completeness'] == 'complete'\n"
            "assert m3['total_tokens'] == 20\n"
            "print('RETRIEVAL_OK')\n"
        )
        proc = subprocess.run([sys.executable, "-c", script, ADAPTERS_DIR, refs_file],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, "stderr: %s\nstdout: %s" % (proc.stderr, proc.stdout))
        self.assertIn("RETRIEVAL_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
