"""Tests for scripts/ases_gate.py (standard library only).

Run from the repository root:  python -m unittest discover -s tests -v
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ases_gate.py"
sys.path.insert(0, str(ROOT / "scripts"))
import ases_verify as av  # noqa: E402

SNAP = "docs/governance/ases"
LOCK = "docs/governance/ases.lock.json"
RECORD = "docs/governance/ases-approvals/adoption.md"
CONTEXT = "docs/governance/PROJECT_CONTEXT.md"
TASK = "docs/governance/CURRENT_TASK.md"

CONTEXT_TEXT = """# PROJECT CONTEXT

## 1. Project Identity

- Project name: Sample Project
- Project ID: SAMPLE-001
- Repository: https://example.invalid/sample
- Primary branch: main
- Owner: Sample Owner

## 2. Business Problem and Users

The sample project solves a verified business problem for a defined group of users and records the
expected business outcome without inventing unapproved requirements.

## 3. Scope

### In scope

- Implement the sample requirement.

### Out of scope

- Unrelated capabilities.

## 4. Requirements

| ID | Type | Requirement | Acceptance criteria | Status |
|---|---|---|---|---|
| REQ-001 | Functional | The system shall perform the sample action. | The action succeeds and is observable. | Specified |
| REQ-002 | Non-functional | The system shall not write secrets to logs. | No secret appears in test logs. | Specified |

## 5. Architecture and Data

- Data storage: local files
- API/integration: N/A (no external API)
- Authentication/authorization: local operator only
- Error handling: fail closed with a clear message
- Deployment: local process
- Backup/recovery: source controlled; no runtime data

## 6. Security and Quality

- Secrets: none stored in the repository
- Permissions: read-only except the authorized file
- Input validation: validate sample input
- Audit logging: record the sample action
- Dependency and supply-chain risk: standard library only
- Test strategy summary: unit tests
- Known security limitations: local tool only

## 7. Delivery Plan

- Milestones: M1
- Test strategy: unit and CLI tests
- Risks: test environment differences
- Dependencies: Python standard library
- Rollback plan: revert the commit
- Evidence required at each gate: commands and results

## 8. Current Milestone

- Milestone ID: M1
- Objective: implement REQ-001
- Authorized scope: the sample file
- Acceptance criteria: REQ-001 passes
- Status: Planned
- Target date: 2026-12-01
- Evidence location: docs/governance/evidence

## 9. Founder Decisions

- Approved decisions: docs/governance/APPROVED_DECISIONS.md
- Locked constraints: the Constitution and this context
- Open proposals (not approved): none
- Exceptions approved by the Founder: none
"""

TASK_TEXT = """# CURRENT TASK

- Task ID: TASK-001
- Project: SAMPLE-001
- Agent: test-agent
- Requested by: Founder
- Date: 2026-11-20
- Status: Authorized
- Objective: Implement the sample requirement.
- Authorized scope: REQ-001 only.
- Files/modules allowed: src/sample.py
- Prohibited actions: Do not change the Constitution.
- Implementation requirements: Preserve the approved architecture.
- Testing requirements: Run unit tests.
- Acceptance criteria: REQ-001 passes.
- Approved decisions reference: docs/governance/APPROVED_DECISIONS.md
- Authorization evidence: https://example.invalid/approvals/1
"""


def cli(*args, cwd=None):
    proc = subprocess.run([sys.executable, "-I", str(SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    return proc.returncode, proc.stdout + proc.stderr


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def copy_release(dest):
    for rel in list(av.MANAGED_FILES) + [av.MANIFEST_NAME]:
        put(Path(dest) / rel, (ROOT / rel).read_bytes())


def record_text(manifest_sha, version):
    fields = {
        "record_schema": "ases-approval/1", "from_version": "none", "to_version": version,
        "to_manifest_sha256": manifest_sha, "change_request": "none", "diff_reviewed": "not-applicable",
        "founder_decision": "Approved", "founder_approval_date": "2026-11-20",
        "evidence": "test fixture reference",
    }
    body = "".join("%s: %s\n" % (k, v) for k, v in fields.items())
    return "---\n" + body + "---\n\n# record\n"


def make_project(base):
    base = Path(base)
    copy_release(base / SNAP)
    real = av.real_root(str(base))
    manifest, manifest_sha = av.snapshot_manifest(real, SNAP)
    put(base / RECORD, record_text(manifest_sha, manifest["ases_version"]))
    lock = av.build_lock(real, SNAP, av.DEFAULT_REPOSITORY, None, RECORD)
    put(base / LOCK, av.dump_json(lock))
    put(base / CONTEXT, CONTEXT_TEXT)
    put(base / TASK, TASK_TEXT)
    return base, lock


def tree_state(base):
    state = []
    for dirpath, dirnames, filenames in os.walk(str(base)):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            st = os.stat(full)
            with open(full, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            state.append((os.path.relpath(full, str(base)), st.st_size, st.st_mtime_ns, digest))
        for name in dirnames:
            state.append((os.path.relpath(os.path.join(dirpath, name), str(base)), "dir"))
    return state


class GateBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.project, self.lock = make_project(self.dir / "project")

    def gate(self, *extra):
        return cli("check", "--project-root", self.project, *extra)

    def assertBlocked(self, code, *extra):
        rc, out = self.gate(*extra)
        self.assertEqual(rc, 1, out)
        self.assertIn("[%s]" % code, out)
        self.assertIn("RESULT: BLOCKED", out)
        return out

    def replace(self, rel, old, new):
        path = self.project / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        put(path, text.replace(old, new))


class ValidGate(GateBase):
    def test_valid_project_passes(self):
        rc, out = self.gate()
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT: PASS", out)
        self.assertIn("ASES snapshot, lock and approval record verify", out)
        self.assertIn("cannot prove that a Founder approval is genuine", out)

    def test_gate_is_read_only(self):
        before = tree_state(self.project)
        self.assertEqual(self.gate()[0], 0)
        self.assertEqual(before, tree_state(self.project))
        put(self.project / TASK, TASK_TEXT.replace("Status: Authorized", "Status: Proposed"))
        before = tree_state(self.project)
        self.assertEqual(self.gate()[0], 1)
        self.assertEqual(before, tree_state(self.project))


class ContextChecks(GateBase):
    def test_missing_context(self):
        os.remove(self.project / CONTEXT)
        self.assertBlocked("CONTEXT_MISSING")

    def test_incomplete_context(self):
        put(self.project / CONTEXT, "# PROJECT CONTEXT\n\n## 1. Project Identity\n\n- Project name: X\n")
        out = self.assertBlocked("CONTEXT_SECTION_MISSING")
        self.assertIn("requirements", out)

    def test_context_placeholders(self):
        self.replace(CONTEXT, "- Owner: Sample Owner", "- Owner: <owner>")
        self.assertBlocked("CONTEXT_PLACEHOLDER")

    def test_context_requires_nonfunctional_requirement(self):
        self.replace(CONTEXT, "| REQ-002 | Non-functional |", "| REQ-002 | Data |")
        self.assertBlocked("CONTEXT_REQUIREMENTS")

    def test_context_requires_scope(self):
        self.replace(CONTEXT, "- Unrelated capabilities.", "")
        self.assertBlocked("CONTEXT_SCOPE")

    def test_context_milestone_status(self):
        self.replace(CONTEXT, "- Status: Planned", "- Status: Accepted")
        self.assertBlocked("CONTEXT_MILESTONE")

    def test_context_decisions_reference(self):
        self.replace(CONTEXT, "- Approved decisions: docs/governance/APPROVED_DECISIONS.md",
                     "- Approved decisions: none recorded")
        self.assertBlocked("CONTEXT_DECISIONS")


class TaskChecks(GateBase):
    def test_missing_task(self):
        os.remove(self.project / TASK)
        self.assertBlocked("TASK_MISSING")

    def test_task_not_authorized(self):
        self.replace(TASK, "Status: Authorized", "Status: Proposed")
        self.assertBlocked("TASK_NOT_AUTHORIZED")

    def test_task_project_mismatch(self):
        self.replace(TASK, "- Project: SAMPLE-001", "- Project: OTHER-001")
        self.assertBlocked("TASK_PROJECT_MISMATCH")

    def test_task_placeholder(self):
        self.replace(TASK, "- Objective: Implement the sample requirement.", "- Objective: <fill in>")
        self.assertBlocked("TASK_PLACEHOLDER")

    def test_task_invalid_date(self):
        self.replace(TASK, "- Date: 2026-11-20", "- Date: 2026-13-40")
        self.assertBlocked("TASK_FIELD_INVALID")

    def test_task_self_authorization_rejected(self):
        self.replace(TASK, "Authorization evidence: https://example.invalid/approvals/1",
                     "Authorization evidence: self")
        self.assertBlocked("TASK_FIELD_INVALID")

    def test_task_may_reference_no_approved_decisions(self):
        self.replace(TASK, "- Approved decisions reference: docs/governance/APPROVED_DECISIONS.md",
                     "- Approved decisions reference: none")
        self.assertEqual(self.gate()[0], 0)


class SnapshotChecks(GateBase):
    def test_tampered_snapshot(self):
        path = self.project / SNAP / "CONSTITUTION.md"
        path.write_bytes(path.read_bytes() + b"tampered\n")
        self.assertBlocked("SNAPSHOT_FILE_MODIFIED")

    def test_snapshot_without_lock(self):
        os.remove(self.project / LOCK)
        self.assertBlocked("SNAPSHOT_LOCK_MISSING")

    def test_no_constitution_and_no_snapshot(self):
        shutil.rmtree(self.project / SNAP)
        os.remove(self.project / LOCK)
        self.assertBlocked("CONSTITUTION_MISSING")


if __name__ == "__main__":
    unittest.main()
