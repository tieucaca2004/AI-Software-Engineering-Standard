"""Tests for scripts/ases_gate.py (standard library only).

Run from the repository root:  python -m unittest discover -s tests -v
"""
import hashlib
import json
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
import ases_gate as gate  # noqa: E402

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
    put(base / "docs/governance/APPROVED_DECISIONS.md",
        "# APPROVED DECISIONS\n\nNo decisions recorded in this test fixture.\n")
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

    def test_usage_errors_exit_2(self):
        self.assertEqual(cli()[0], 2)
        self.assertEqual(cli("check", "--project-root", self.dir / "missing")[0], 2)

    def test_non_adopted_project_with_root_constitution_passes(self):
        plain = self.dir / "plain"
        put(plain / "CONSTITUTION.md", (ROOT / "CONSTITUTION.md").read_bytes())
        put(plain / CONTEXT, CONTEXT_TEXT)
        put(plain / TASK, TASK_TEXT)
        put(plain / "docs/governance/APPROVED_DECISIONS.md",
            "# APPROVED DECISIONS\n\nNo decisions recorded in this test fixture.\n")
        rc, out = cli("check", "--project-root", plain)
        self.assertEqual(rc, 0, out)
        self.assertIn("Root CONSTITUTION.md is present", out)

    def test_gate_works_with_network_blocked(self):
        code = (
            "import socket, runpy, sys\n"
            "def blocked(*a, **k):\n    raise RuntimeError('network access attempted')\n"
            "socket.socket = blocked; socket.create_connection = blocked; socket.getaddrinfo = blocked\n"
            "sys.argv = [%r, 'check', '--project-root', %r]\n"
            "runpy.run_path(%r, run_name='__main__')\n" % (str(SCRIPT), str(self.project), str(SCRIPT)))
        proc = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

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

    def test_context_decisions_file_missing(self):
        os.remove(self.project / "docs/governance/APPROVED_DECISIONS.md")
        out = self.assertBlocked("CONTEXT_DECISIONS")
        self.assertIn("approved decisions file not found", out)


class BulletParserUnit(unittest.TestCase):
    """Unit tests for the multiline bullet parser in scripts/ases_gate.py."""

    @staticmethod
    def bullets(text):
        return [m.group(1) for m in gate.BULLET.finditer(text) if gate.structured(m.group(1))]

    def test_multiple_bullets_across_lines(self):
        self.assertEqual(self.bullets("- a\n- b\n- c"), ["a", "b", "c"])

    def test_single_bullet(self):
        self.assertEqual(self.bullets("- only item"), ["only item"])

    def test_leading_spaces_and_tabs(self):
        self.assertEqual(self.bullets("  - spaced\n\t- tabbed\n- plain"), ["spaced", "tabbed", "plain"])

    def test_empty_subsection(self):
        self.assertEqual(self.bullets(""), [])

    def test_heading_and_text_without_bullets(self):
        self.assertEqual(self.bullets("### Sub\n\nplain text no dash"), [])

    def test_empty_bullet_entries_filtered(self):
        self.assertEqual(self.bullets("- \n- real"), ["real"])

    def test_star_bullets(self):
        self.assertEqual(self.bullets("* a\n* b"), ["a", "b"])

    def test_adjacent_subsections_are_independent(self):
        section = "### In scope\n\n- a\n\n### Out of scope\n\n- b"
        self.assertEqual(self.bullets(gate.subsection(section, "In scope")), ["a"])
        self.assertEqual(self.bullets(gate.subsection(section, "Out of scope")), ["b"])


class BulletScopeIntegration(GateBase):
    """Gate-level regression tests for multiline scope bullets."""

    def test_multiple_in_scope_bullets_pass(self):
        self.replace(CONTEXT, "- Implement the sample requirement.",
                     "- Implement the sample requirement.\n- Verify the sample requirement.")
        rc, out = self.gate()
        self.assertEqual(rc, 0, out)

    def test_leading_whitespace_bullet_passes(self):
        self.replace(CONTEXT, "- Implement the sample requirement.", "  - Implement the sample requirement.")
        rc, out = self.gate()
        self.assertEqual(rc, 0, out)

    def test_empty_scope_bullets_still_blocked(self):
        self.replace(CONTEXT, "- Implement the sample requirement.", "")
        self.replace(CONTEXT, "- Unrelated capabilities.", "")
        self.assertBlocked("CONTEXT_SCOPE")

    def test_text_without_bullets_blocked(self):
        self.replace(CONTEXT, "- Implement the sample requirement.", "This is not a bullet.")
        self.assertBlocked("CONTEXT_SCOPE")

    def test_empty_bullet_entry_blocked(self):
        self.replace(CONTEXT, "- Implement the sample requirement.", "- ")
        self.assertBlocked("CONTEXT_SCOPE")


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


class ScopeChecks(GateBase):
    def changed(self, *paths):
        put(self.project / "changed-files.txt", "\n".join(paths) + "\n")
        return "changed-files.txt"

    def test_scope_accepts_allowed_file(self):
        rc, out = self.gate("--changed-files", self.changed("src/sample.py"))
        self.assertEqual(rc, 0, out)

    def test_scope_blocks_unlisted_file(self):
        out = self.assertBlocked("TASK_SCOPE_VIOLATION",
                                 "--changed-files", self.changed("src/other.py"))
        self.assertIn("src/other.py", out)

    def test_scope_accepts_glob(self):
        self.replace(TASK, "Files/modules allowed: src/sample.py",
                     "Files/modules allowed: src/*.py")
        rc, out = self.gate("--changed-files", self.changed("src/sample.py"))
        self.assertEqual(rc, 0, out)

    def test_scope_accepts_comma_separated_patterns(self):
        self.replace(TASK, "Files/modules allowed: src/sample.py",
                     "Files/modules allowed: docs/**, src/*.py")
        rc, out = self.gate("--changed-files", self.changed("src/sample.py"))
        self.assertEqual(rc, 0, out)

    def test_scope_rejects_unsafe_allowed_pattern(self):
        self.replace(TASK, "Files/modules allowed: src/sample.py",
                     "Files/modules allowed: ../outside.py")
        self.assertBlocked("TASK_FIELD_INVALID",
                           "--changed-files", self.changed("src/sample.py"))

    def test_scope_accepts_explicit_all(self):
        self.replace(TASK, "Files/modules allowed: src/sample.py",
                     "Files/modules allowed: all")
        rc, out = self.gate("--changed-files", self.changed("docs/readme.md"))
        self.assertEqual(rc, 0, out)

    def test_scope_rejects_traversal(self):
        self.assertBlocked("TASK_CHANGED_FILES_INVALID",
                           "--changed-files", self.changed("../outside.py"))

    def test_scope_missing_changed_file(self):
        self.assertBlocked("TASK_CHANGED_FILES_MISSING",
                           "--changed-files", "missing.txt")

    def test_scope_blocks_task_record_change(self):
        self.assertBlocked("TASK_SCOPE_VIOLATION", "--changed-files",
                           self.changed("docs/governance/CURRENT_TASK.md"))


class AdoptedProjectCI(GateBase):
    """Exercise the adopted-project CI commands on a real temporary Git repository."""

    def setUp(self):
        super().setUp()
        self.git = shutil.which("git")
        if not self.git:
            self.skipTest("git is not available")
        put(self.project / "src/sample.py", "baseline\n")
        put(self.project / "src/other.py", "baseline\n")
        put(self.project / "docs/other.md", "baseline\n")
        put(self.project / ".github/workflows/ases-governance.yml",
            (ROOT / "templates" / "ases-governance.yml").read_bytes())
        self.run_git("init", "-b", "main")
        self.run_git("config", "user.email", "test@example.invalid")
        self.run_git("config", "user.name", "ASES test")
        self.run_git("add", "-A")
        self.run_git("commit", "-m", "adopted project baseline")

    def run_git(self, *args):
        proc = subprocess.run([self.git, "-C", str(self.project), *args],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def changed_files(self):
        return [line for line in self.run_git("diff", "--name-only", "HEAD").stdout.splitlines() if line]

    def changed_list(self, *paths):
        put(self.project / "changed-files.txt", "\n".join(paths) + "\n")
        return "changed-files.txt"

    def test_adopted_ci_valid_repository_passes(self):
        put(self.project / "src/sample.py", "changed\n")
        paths = self.changed_files()
        self.assertEqual(paths, ["src/sample.py"])
        rc, out = self.gate("--changed-files", self.changed_list(*paths))
        self.assertEqual(rc, 0, out)

    def test_adopted_ci_missing_context_fails(self):
        os.remove(self.project / CONTEXT)
        rc, out = self.gate("--changed-files", self.changed_list(*self.changed_files()))
        self.assertEqual(rc, 1, out)
        self.assertIn("[CONTEXT_MISSING]", out)

    def test_adopted_ci_missing_task_fails(self):
        os.remove(self.project / TASK)
        rc, out = self.gate("--changed-files", self.changed_list(*self.changed_files()))
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_MISSING]", out)

    def test_adopted_ci_out_of_scope_change_fails(self):
        put(self.project / "docs/other.md", "changed\n")
        paths = self.changed_files()
        self.assertIn("docs/other.md", paths)
        rc, out = self.gate("--changed-files", self.changed_list(*paths))
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_SCOPE_VIOLATION] docs/other.md", out)


class AutoCollectScope(AdoptedProjectCI):
    """Scope enforcement via the explicit legacy full-tree collector (--legacy-collect)."""

    def gate_legacy(self):
        return self.gate("--legacy-collect")

    def test_in_scope_change_passes(self):
        put(self.project / "src/sample.py", "changed\n")
        rc, out = self.gate_legacy()
        self.assertEqual(rc, 0, out)

    def test_out_of_scope_change_blocks(self):
        put(self.project / "docs/other.md", "changed\n")
        rc, out = self.gate_legacy()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_SCOPE_VIOLATION] docs/other.md", out)

    def test_multiple_changes_with_one_out_of_scope_blocks(self):
        put(self.project / "src/sample.py", "changed\n")
        put(self.project / "docs/other.md", "changed\n")
        rc, out = self.gate_legacy()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_SCOPE_VIOLATION] docs/other.md", out)

    def test_untracked_in_scope_passes(self):
        # widen scope and commit it first so the task-record change is in the baseline
        self.replace(TASK, "Files/modules allowed: src/sample.py",
                     "Files/modules allowed: src/*.py")
        self.run_git("add", "-A")
        self.run_git("commit", "-m", "widen scope for untracked test")
        put(self.project / "src/newfile.py", "new\n")
        rc, out = self.gate_legacy()
        self.assertEqual(rc, 0, out)

    def test_untracked_out_of_scope_blocks(self):
        put(self.project / "docs/newfile.md", "new\n")
        rc, out = self.gate_legacy()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_SCOPE_VIOLATION]", out)

    def test_deleted_out_of_scope_file_blocks(self):
        os.remove(self.project / "docs/other.md")
        rc, out = self.gate_legacy()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_SCOPE_VIOLATION]", out)


class BaselineIsolation(AdoptedProjectCI):
    """Per-work-unit baseline snapshot and delta isolation (B01-B20 core)."""

    def capture(self, wu="WU1"):
        return cli("baseline", "--project-root", self.project, "--work-unit", wu,
                   "--output", "baseline.json")

    def check_delta(self, wu="WU1"):
        return cli("check", "--project-root", self.project,
                   "--baseline", "baseline.json", "--work-unit", wu)

    def read_baseline(self):
        import json
        return json.loads((self.project / "baseline.json").read_text(encoding="utf-8"))

    def delta(self, wu="WU1"):
        import ases_verify as av2
        root = av2.real_root(str(self.project))
        baseline = json.loads((self.project / "baseline.json").read_text(encoding="utf-8"))
        findings = []
        paths = gate.compute_delta(root, baseline, wu, findings)
        return [p for p in paths if p != "baseline.json"], findings

    # B01 pre-existing in-scope change (captured in baseline) is not attributed
    def test_pre_existing_in_scope_not_attributed(self):
        put(self.project / "src/sample.py", "pre-existing\n")
        self.capture()
        rc, out = self.check_delta()
        self.assertEqual(rc, 0, out)

    # B02 pre-existing out-of-scope change (captured in baseline) is not attributed
    def test_pre_existing_out_of_scope_not_attributed(self):
        put(self.project / "docs/other.md", "pre-existing out-of-scope\n")
        self.capture()
        rc, out = self.check_delta()
        self.assertEqual(rc, 0, out)

    # B03 new in-scope change is detected and passes
    def test_new_in_scope_detected_and_passes(self):
        self.capture()
        put(self.project / "src/sample.py", "work-unit change\n")
        rc, out = self.check_delta()
        self.assertEqual(rc, 0, out)

    # B04 new out-of-scope change is detected and blocks
    def test_new_out_of_scope_blocks(self):
        self.capture()
        put(self.project / "docs/other.md", "work-unit out-of-scope\n")
        rc, out = self.check_delta()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_SCOPE_VIOLATION] docs/other.md", out)

    # B05 pre-existing out-of-scope change reverted is detected
    def test_reverted_pre_existing_detected(self):
        put(self.project / "docs/other.md", "pre-existing out-of-scope\n")
        self.capture()
        put(self.project / "docs/other.md", "baseline\n")  # revert to committed content
        paths, findings = self.delta()
        self.assertIn("docs/other.md", paths)
        self.assertEqual(findings, [])

    # B07 new untracked out-of-scope file blocks
    def test_new_untracked_out_of_scope_blocks(self):
        self.capture()
        put(self.project / "docs/newfile.md", "new out-of-scope\n")
        rc, out = self.check_delta()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_SCOPE_VIOLATION]", out)

    # B10 deleted tracked file is detected
    def test_deleted_tracked_file_detected(self):
        self.capture()
        os.remove(self.project / "docs/other.md")
        paths, findings = self.delta()
        self.assertIn("docs/other.md", paths)

    # B13 missing baseline blocks
    def test_missing_baseline_blocks(self):
        rc, out = self.check_delta()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_BASELINE_MISSING]", out)

    # B14 baseline from a different repository blocks
    def test_baseline_repo_mismatch_blocks(self):
        self.capture()
        baseline = self.read_baseline()
        baseline["repository_root"] = "C:/somewhere/else"
        put(self.project / "baseline.json", json.dumps(baseline, indent=2))
        rc, out = self.check_delta()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_BASELINE_INVALID]", out)

    # B15 work-unit id mismatch blocks
    def test_workunit_mismatch_blocks(self):
        self.capture("WU1")
        rc, out = self.check_delta("WU2")
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_BASELINE_INVALID]", out)

    # B19 change then restore original content -> no attribution
    def test_change_and_restore_no_attribution(self):
        self.capture()
        put(self.project / "src/sample.py", "temporary\n")
        put(self.project / "src/sample.py", "baseline\n")  # restore committed content
        paths, findings = self.delta()
        self.assertEqual(paths, [])

    # B20 a pre-existing untracked artifact (like milestone-1.diff) is not attributed
    def test_pre_existing_untracked_not_attributed(self):
        put(self.project / "artifact.diff", "untracked evidence\n")
        self.capture()
        rc, out = self.check_delta()
        self.assertEqual(rc, 0, out)

    # B12: capture in a directory that is not its own git work tree fails closed
    def test_baseline_capture_fails_non_own_repo(self):
        plain = self.dir / "plain-not-own-repo"
        plain.mkdir(parents=True, exist_ok=True)
        put(plain / "x.txt", "x\n")
        with self.assertRaises(OSError):
            gate.capture_baseline(av.real_root(str(plain)), "WU1")

    # B16: final-state collection failure blocks (remove .git after baseline)
    def test_final_state_collection_failure_blocks(self):
        import stat
        self.capture()

        def rmtree(p):
            for root, dirs, files in os.walk(p, topdown=False):
                for n in files:
                    fp = os.path.join(root, n)
                    try:
                        os.chmod(fp, stat.S_IWRITE)
                        os.unlink(fp)
                    except OSError:
                        pass
                for n in dirs:
                    dp = os.path.join(root, n)
                    try:
                        os.chmod(dp, stat.S_IWRITE)
                        os.rmdir(dp)
                    except OSError:
                        pass
            try:
                os.rmdir(p)
            except OSError:
                pass

        rmtree(self.project / ".git")
        rc, out = self.check_delta()
        self.assertEqual(rc, 1, out)
        self.assertIn("[TASK_BASELINE_INVALID]", out)


class IntentChecks(GateBase):
    """IISE intent-integrity & scope deterministic decision tests (A-F)."""

    def intent(self, instruction, source="agent"):
        return cli("intent", "--project-root", self.project, "--instruction", instruction, "--source", source)

    def test_legitimate_in_scope_allows(self):
        rc, out = self.intent("Implement the sample requirement in src/sample.py", "founder")
        self.assertEqual(rc, 0, out)
        self.assertIn('"decision": "ALLOW"', out)

    def test_out_of_scope_objective_requires_founder(self):
        rc, out = self.intent("redirect development to Universal-Orchestrator")
        self.assertEqual(rc, 2, out)
        self.assertIn("REQUIRE_FOUNDER_APPROVAL", out)

    def test_out_of_scope_path_blocks(self):
        rc, out = self.intent("modify src/other.py")
        self.assertEqual(rc, 1, out)
        self.assertIn('"decision": "BLOCK"', out)

    def test_commit_push_blocks(self):
        rc, out = self.intent("commit and push the changes now")
        self.assertEqual(rc, 1, out)

    def test_governance_change_requires_founder(self):
        rc, out = self.intent("rewrite the CONSTITUTION")
        self.assertEqual(rc, 2, out)
        self.assertIn("REQUIRE_FOUNDER_APPROVAL", out)

    def test_credential_access_blocks(self):
        rc, out = self.intent("read the credential value", "tool-output")
        self.assertEqual(rc, 1, out)

    def test_ambiguous_review_required(self):
        rc, out = self.intent("do something vague")
        self.assertEqual(rc, 2, out)
        self.assertIn("REVIEW_REQUIRED", out)

    def test_commit_with_founder_approval_allows(self):
        approval = {"schema": "ases-approval/1", "operations": ["commit", "push"],
                    "work_unit_id": "WU1", "founder_approval_date": "2026-11-22",
                    "evidence": "Founder directive A6"}
        put(self.project / "docs/governance/approvals/commit.json", json.dumps(approval, indent=2))
        rc, out = cli("intent", "--project-root", self.project, "--instruction", "commit and push",
                      "--source", "founder", "--approval", "docs/governance/approvals/commit.json")
        self.assertEqual(rc, 0, out)
        self.assertIn('"decision": "ALLOW"', out)

    def test_force_push_not_covered_by_commit_approval(self):
        approval = {"schema": "ases-approval/1", "operations": ["commit", "push"],
                    "work_unit_id": "WU1", "founder_approval_date": "2026-11-22",
                    "evidence": "Founder directive A6"}
        put(self.project / "docs/governance/approvals/commit.json", json.dumps(approval, indent=2))
        rc, out = cli("intent", "--project-root", self.project, "--instruction", "force-push",
                      "--source", "agent", "--approval", "docs/governance/approvals/commit.json")
        self.assertEqual(rc, 1, out)
        self.assertIn('"decision": "BLOCK"', out)


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
