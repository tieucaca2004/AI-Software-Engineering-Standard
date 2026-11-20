"""Tests for scripts/ases_identity.py and its integration with ases_gate.py."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import ases_identity as ai  # noqa: E402
import test_ases_gate as tg  # noqa: E402


def record(**overrides):
    data = {
        "schema_version": 3,
        "title": "",
        "description": "",
        "acceptance_criteria": [],
        "required_capabilities": [],
        "required_roles": [],
        "scope": "",
        "expected_output": "",
        "execution_constraints": [],
        "depends_on": [],
    }
    data.update(overrides)
    return data


def sample():
    return record(
        title="Build sample",
        description="Build the sample feature",
        acceptance_criteria=["ac1", "ac2"],
        required_capabilities=["coding"],
        required_roles=["agent"],
        scope="sample",
        expected_output="working implementation",
        execution_constraints=["no-production"],
        depends_on=["dep1", "dep2"],
    )


class IdentityHash(unittest.TestCase):
    def test_deterministic_and_format(self):
        digest = ai.compute_identity_hash(sample())
        self.assertEqual(digest, ai.compute_identity_hash(sample()))
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower())
        self.assertEqual(int(digest, 16), int(digest, 16))  # hex digits

    def test_matches_sha256_of_canonical_json(self):
        payload = {field: sample()[field] for field in ai.IDENTITY_FIELDS}
        expected = hashlib.sha256(ai.canonical_json(payload).encode("utf-8")).hexdigest()
        self.assertEqual(ai.compute_identity_hash(sample()), expected)

    def test_input_key_order_does_not_matter(self):
        a = sample()
        b = {k: a[k] for k in reversed(list(a.keys()))}
        self.assertEqual(ai.compute_identity_hash(a), ai.compute_identity_hash(b))

    def test_acceptance_criteria_order_preserved(self):
        a = sample()
        a["acceptance_criteria"] = ["a", "b"]
        b = sample()
        b["acceptance_criteria"] = ["b", "a"]
        self.assertNotEqual(ai.compute_identity_hash(a), ai.compute_identity_hash(b))

    def test_acceptance_criteria_duplicates_preserved(self):
        a = sample()
        a["acceptance_criteria"] = ["a", "a"]
        b = sample()
        b["acceptance_criteria"] = ["a"]
        self.assertNotEqual(ai.compute_identity_hash(a), ai.compute_identity_hash(b))

    def test_depends_on_dedup_keep_first(self):
        a = sample()
        a["depends_on"] = ["a", "b", "a"]
        b = sample()
        b["depends_on"] = ["a", "b"]
        self.assertEqual(ai.compute_identity_hash(a), ai.compute_identity_hash(b))
        b["depends_on"] = ["b", "a"]
        self.assertNotEqual(ai.compute_identity_hash(a), ai.compute_identity_hash(b))

    def test_set_ordering_invariance(self):
        a = sample()
        a["required_capabilities"] = ["b", "a"]
        b = sample()
        b["required_capabilities"] = ["a", "b"]
        self.assertEqual(ai.compute_identity_hash(a), ai.compute_identity_hash(b))

    def test_set_deduplication(self):
        a = sample()
        a["required_roles"] = ["r", "r", "s"]
        b = sample()
        b["required_roles"] = ["r", "s"]
        self.assertEqual(ai.compute_identity_hash(a), ai.compute_identity_hash(b))

    def test_nfc_equivalence(self):
        a = sample()
        a["title"] = "\u00e9"  # e-acute NFC
        b = sample()
        b["title"] = "e\u0301"  # e + combining acute (NFD)
        self.assertEqual(ai.compute_identity_hash(a), ai.compute_identity_hash(b))

    def test_empty_values_valid(self):
        self.assertEqual(len(ai.compute_identity_hash(record())), 64)


class IdentityValidation(unittest.TestCase):
    def assertInvalid(self, data):
        with self.assertRaises(ai.IdentityError) as ctx:
            ai.compute_identity_hash(data)
        self.assertIn("INVALID", str(ctx.exception))

    def test_extra_risk_level_rejected(self):
        data = sample()
        data["risk_level"] = "low"
        self.assertInvalid(data)

    def test_extra_planned_task_id_rejected(self):
        data = sample()
        data["planned_task_id"] = "T-1"
        self.assertInvalid(data)

    def test_missing_field_rejected(self):
        data = sample()
        del data["title"]
        self.assertInvalid(data)

    def test_null_rejected(self):
        data = sample()
        data["scope"] = None
        self.assertInvalid(data)

    def test_wrong_type_rejected(self):
        data = sample()
        data["required_capabilities"] = "coding"
        self.assertInvalid(data)

    def test_nested_object_rejected(self):
        data = sample()
        data["acceptance_criteria"] = [{"x": 1}]
        self.assertInvalid(data)

    def test_wrong_schema_version_rejected(self):
        data = sample()
        data["schema_version"] = 2
        self.assertInvalid(data)

    def test_missing_schema_version_rejected(self):
        data = sample()
        del data["schema_version"]
        self.assertInvalid(data)


class IdentityCli(unittest.TestCase):
    def test_hash_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.json"
            path.write_text(json.dumps(sample()), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "ases_identity.py"),
                                   "hash", str(path)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.strip(), ai.compute_identity_hash(sample()))

    def test_validate_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.json"
            bad = sample()
            bad["scope"] = None
            path.write_text(json.dumps(bad), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "ases_identity.py"),
                                   "validate", str(path)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("INVALID_CANONICAL_TASK", proc.stderr)


class GateIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project, _ = tg.make_project(Path(self._tmp.name) / "project")

    def write_identity(self, data):
        path = self.project / "identity.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return "identity.json"

    def test_gate_valid_identity(self):
        rel = self.write_identity(sample())
        rc, out = tg.cli("check", "--project-root", self.project, "--identity", rel)
        self.assertEqual(rc, 0, out)
        self.assertIn("Identity hash:", out)

    def test_gate_invalid_identity(self):
        bad = sample()
        del bad["title"]
        rel = self.write_identity(bad)
        rc, out = tg.cli("check", "--project-root", self.project, "--identity", rel)
        self.assertEqual(rc, 1, out)
        self.assertIn("[IDENTITY_INVALID]", out)


if __name__ == "__main__":
    unittest.main()
