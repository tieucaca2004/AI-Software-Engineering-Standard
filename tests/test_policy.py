"""Repository-level policy checks: standard files, lifecycle and CI wiring."""
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ases_verify as av  # noqa: E402
import check_policy  # noqa: E402


class PolicyFiles(unittest.TestCase):
    def test_check_policy_passes(self):
        proc = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "check_policy.py")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASSED", proc.stdout)

    def test_preflight_passes(self):
        proc = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "ases_preflight.py"),
                               "--project-root", str(ROOT)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("MANDATORY READING SEQUENCE", proc.stdout)

    def test_constitution_hash_constant_matches_repository(self):
        self.assertEqual(av.file_hash(ROOT / "CONSTITUTION.md"), check_policy.CONSTITUTION_SHA256)

    def test_check_policy_rejects_tampered_constitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            for rel in check_policy.REQUIRED:
                target = temp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / rel, target)
            with open(temp / "CONSTITUTION.md", "ab") as handle:
                handle.write(b"\nTAMPER\n")
            old_root = check_policy.ROOT
            check_policy.ROOT = temp
            try:
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    rc = check_policy.main()
            finally:
                check_policy.ROOT = old_root
            self.assertEqual(rc, 1, buffer.getvalue())
            self.assertIn("does not match the approved Constitution 1.0 hash", buffer.getvalue())

            proc = subprocess.run(
                [sys.executable, "-I", str(ROOT / "scripts" / "ases_verify.py"),
                 "manifest", "--check", "--source-root", str(temp)],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("stale", proc.stdout)

    def test_version_matches_manifest(self):
        import json
        manifest = json.loads((ROOT / "ases-manifest.json").read_text(encoding="utf-8"))
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(manifest["ases_version"], version)

    def test_lifecycle_document_has_all_gates(self):
        text = (ROOT / "docs" / "LIFECYCLE_GATES.md").read_text(encoding="utf-8")
        for gate in ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7"):
            self.assertIn(gate, text)
        self.assertIn("Founder", text)
        self.assertIn("not evidence", text)

    def test_ci_runs_policy_manifest_preflight_and_tests(self):
        text = (ROOT / ".github" / "workflows" / "ases-policy.yml").read_text(encoding="utf-8")
        for command in ("scripts/check_policy.py", "ases_preflight.py", "manifest --check",
                        "unittest discover"):
            self.assertIn(command, text)

    def test_adopted_workflow_template_runs_verify_and_gate(self):
        text = (ROOT / "templates" / "ases-governance.yml").read_text(encoding="utf-8")
        for needle in ("ases_verify.py verify", "ases_gate.py check", "CURRENT_TASK.md",
                       "--changed-files", "fetch-depth: 0"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
