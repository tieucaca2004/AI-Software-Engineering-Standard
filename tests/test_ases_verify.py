"""Tests for scripts/ases_verify.py (standard library only).

Run from the repository root:  python -m unittest discover -s tests -v
"""
import ast
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
SCRIPT = ROOT / "scripts" / "ases_verify.py"
sys.path.insert(0, str(ROOT / "scripts"))
import ases_verify as av  # noqa: E402

SNAP = "docs/governance/ases"
LOCK = "docs/governance/ases.lock.json"
RECORD = "docs/governance/ases-approvals/adoption.md"
A_LF_SHA = "87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7"  # sha256 of b"a\n"


def cli(*args, cwd=None):
    proc = subprocess.run([sys.executable, "-I", str(SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    return proc.returncode, proc.stdout + proc.stderr


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def copy_release(dest, names=None):
    """Copy the managed files and the manifest from the repository into dest."""
    for rel in list(av.MANAGED_FILES) + [av.MANIFEST_NAME]:
        put(Path(dest) / rel, (ROOT / rel).read_bytes())


def record_text(manifest_sha, version, **overrides):
    fields = {
        "record_schema": "ases-approval/1", "from_version": "none", "to_version": version,
        "to_manifest_sha256": manifest_sha, "change_request": "none", "diff_reviewed": "not-applicable",
        "founder_decision": "Approved", "founder_approval_date": "2026-11-18",
        "evidence": "test fixture reference",
    }
    fields.update(overrides)
    body = "".join("%s: %s\n" % (k, v) for k, v in fields.items())
    return "---\n" + body + "---\n\n# record\n"


def make_project(base):
    base = Path(base)
    copy_release(base / SNAP)
    real = av.real_root(str(base))
    manifest, manifest_sha = av.snapshot_manifest(real, SNAP)
    put(base / RECORD, record_text(manifest_sha, manifest["ases_version"]))  # build_lock requires it first
    lock = av.build_lock(real, SNAP, av.DEFAULT_REPOSITORY, None, RECORD)
    put(base / LOCK, av.dump_json(lock))
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


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.project, self.lock = make_project(self.dir / "project")

    def verify(self, *extra):
        return cli("verify", "--project-root", self.project, *extra)

    def assertFails(self, code, *extra):
        rc, out = self.verify(*extra)
        self.assertEqual(rc, 1, out)
        self.assertIn("[%s]" % code, out)
        self.assertIn("RESULT: FAIL", out)
        return out

    def write_lock(self, mutate):
        data = json.loads((self.project / LOCK).read_text(encoding="utf-8"))
        mutate(data)
        put(self.project / LOCK, json.dumps(data, indent=2))


class ValidAdoption(Base):
    def test_valid_project_passes(self):
        rc, out = self.verify()
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT: PASS", out)
        self.assertIn("DECLARED", out)
        self.assertIn("CANNOT verify that the Founder", out)

    def test_lock_command_is_deterministic_and_matches(self):
        rc, out = cli("lock", "--project-root", self.project, "--approval-record", RECORD)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.encode("ascii").replace(b"\r\n", b"\n"), (self.project / LOCK).read_bytes())

    def test_docs_list_every_managed_file(self):
        text = (ROOT / "docs" / "UAM.md").read_text(encoding="utf-8")
        for rel in av.MANAGED_FILES:
            self.assertIn("`%s`" % rel, text, rel)

    def test_repository_manifest_is_current(self):
        rc, out = cli("manifest", "--check", "--source-root", ROOT)
        self.assertEqual(rc, 0, out)

    def test_manifest_generation_is_deterministic(self):
        first = av.dump_json(av.build_manifest(str(ROOT)))
        self.assertEqual(first, av.dump_json(av.build_manifest(str(ROOT))))
        self.assertEqual(first, av.canonical_text_bytes((ROOT / av.MANIFEST_NAME).read_bytes()))

    def test_stale_manifest_detected(self):
        src = self.dir / "src"
        copy_release(src)
        put(src / "CHANGELOG.md", (src / "CHANGELOG.md").read_bytes() + b"extra\n")
        rc, out = cli("manifest", "--check", "--source-root", src)
        self.assertEqual(rc, 1, out)
        self.assertIn("stale", out)


class Versions(Base):
    def test_expect_version_match_and_mismatch(self):
        self.assertEqual(self.verify("--expect-version", self.lock["ases_version"])[0], 0)
        self.assertFails("VERSION_MISMATCH", "--expect-version", "9.9.9")

    def test_lock_version_differs_from_manifest(self):
        self.write_lock(lambda d: d.update(ases_version="1.0.1"))
        self.assertFails("VERSION_MISMATCH")

    def test_snapshot_version_file_tampered(self):
        put(self.project / SNAP / "VERSION", "2.0.0\n")
        out = self.assertFails("FILE_MODIFIED")
        self.assertIn("[VERSION_MISMATCH]", out)

    def test_invalid_version_format_in_lock(self):
        self.write_lock(lambda d: d.update(ases_version="1.0"))
        self.assertFails("LOCK_INVALID")


class Hashing(unittest.TestCase):
    def test_known_sha256(self):
        self.assertEqual(av.sha256_hex(b"a\n"), A_LF_SHA)
        self.assertEqual(av.sha256_hex(av.canonical_text_bytes(b"a\r\n")), A_LF_SHA)
        self.assertEqual(av.sha256_hex(av.canonical_text_bytes(b"a\n")), A_LF_SHA)

    def test_canonicalization_rules(self):
        self.assertEqual(av.canonical_text_bytes(b"a\r\nb\n"), b"a\nb\n")
        self.assertEqual(av.canonical_text_bytes("é\r\n".encode("utf-8")), "é\n".encode("utf-8"))
        for bad in (b"\xef\xbb\xbfx\n", b"a\rb\n", b"a\r\r\nb", b"\xff\xfe", b"a\x00b", b"\xc3("):
            with self.assertRaises(ValueError, msg=repr(bad)):
                av.canonical_text_bytes(bad)

    def test_crlf_checkout_verifies(self):
        for rel in list(av.MANAGED_FILES) + [av.MANIFEST_NAME]:
            path = self.project_file(rel)
            # the source tree may already be CRLF (Windows autocrlf), so normalize first
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        rc, out = self.verify()
        self.assertEqual(rc, 0, out)
        for rel in ("CONSTITUTION.md", av.MANIFEST_NAME):
            self.assertIn(b"\r\n", self.project_file(rel).read_bytes())

    def test_bom_and_lone_cr_fail(self):
        target = self.project_file("CONSTITUTION.md")
        original = target.read_bytes()
        for bad in (b"\xef\xbb\xbf" + original, original + b"x\rx\n"):
            target.write_bytes(bad)
            rc, out = self.verify()
            self.assertEqual(rc, 1, out)
            self.assertIn("[FILE_MODIFIED] CONSTITUTION.md", out)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project, self.lock = make_project(Path(self._tmp.name) / "project")

    def project_file(self, rel):
        return self.project / SNAP / rel

    def verify(self):
        return cli("verify", "--project-root", self.project)


class FileIntegrity(Base):
    def test_missing_file(self):
        os.remove(self.project / SNAP / "CONSTITUTION.md")
        self.assertFails("FILE_MISSING")

    def test_modified_file(self):
        path = self.project / SNAP / "CONSTITUTION.md"
        path.write_bytes(path.read_bytes() + b"tampered\n")
        out = self.assertFails("FILE_MODIFIED")
        self.assertIn("fix FILE_MODIFIED", out)

    def test_unexpected_file_and_directory_entry(self):
        put(self.project / SNAP / "notes.md", "project file in managed dir\n")
        put(self.project / SNAP / "sub" / "x.txt", "x\n")
        out = self.assertFails("FILE_UNEXPECTED")
        self.assertIn("notes.md", out)
        self.assertIn("sub/x.txt", out)

    def test_manifest_removed_or_modified(self):
        manifest = self.project / SNAP / av.MANIFEST_NAME
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["files"][0]["sha256"] = "0" * 64
        put(manifest, json.dumps(data, indent=2) + "\n")
        self.assertFails("MANIFEST_MISMATCH")
        os.remove(manifest)
        self.assertFails("FILE_MISSING")

    def test_empty_directory_in_snapshot_rejected(self):
        os.makedirs(self.project / SNAP / "empty")
        out = self.assertFails("FILE_UNEXPECTED")
        self.assertIn("empty", out)
        self.assertIn("empty directory", out)

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_junction_in_snapshot_rejected(self):
        docs = self.project / SNAP / "docs"
        outside = self.dir / "outside_docs"
        shutil.copytree(docs, outside)
        shutil.rmtree(docs)
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(docs), str(outside)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            self.skipTest("junction creation not permitted: %s" % (proc.stdout + proc.stderr))
        try:
            out = self.assertFails("FILE_INVALID")
            self.assertIn("junction", out)
        finally:
            if os.path.lexists(docs):
                os.rmdir(docs)

    def test_symlink_in_snapshot_rejected(self):
        victim = self.project / SNAP / "VERSION"
        outside = self.dir / "outside.txt"
        put(outside, (ROOT / "VERSION").read_bytes())
        os.remove(victim)
        try:
            os.symlink(str(outside), str(victim))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not permitted in this environment")
        self.assertFails("FILE_INVALID")


class LockStructure(Base):
    def test_missing_lock(self):
        os.remove(self.project / LOCK)
        self.assertFails("LOCK_MISSING")

    def test_invalid_locks(self):
        good = json.loads((self.project / LOCK).read_text(encoding="utf-8"))

        def mutated(fn):
            data = json.loads(json.dumps(good))
            fn(data)
            return json.dumps(data).encode("utf-8")

        cases = {
            "not json": b"{nope",
            "empty": b"",
            "bom": b"\xef\xbb\xbf" + json.dumps(good).encode("utf-8"),
            "utf16": json.dumps(good).encode("utf-16"),
            "duplicate key": b'{"schema": "ases-lock/1", "schema": "ases-lock/1"}',
            "array root": b"[]",
            "unknown key": mutated(lambda d: d.update(extra=1)),
            "missing key": mutated(lambda d: d.pop("approval")),
            "bad schema": mutated(lambda d: d.update(schema="ases-lock/2")),
            "short hash": mutated(lambda d: d["manifest"].update(sha256="abc")),
            "uppercase hash": mutated(lambda d: d["manifest"].update(sha256=d["manifest"]["sha256"].upper())),
            "bad commit": mutated(lambda d: d["source"].update(commit="abc123")),
            "traversal": mutated(lambda d: d.update(snapshot_dir="../outside")),
            "absolute": mutated(lambda d: d.update(snapshot_dir="/etc")),
            "backslash": mutated(lambda d: d.update(snapshot_dir="docs\\governance")),
            "drive": mutated(lambda d: d.update(snapshot_dir="C:/x")),
            "record inside snapshot": mutated(lambda d: d["approval"].update(record=SNAP + "/r.md")),
            "nan": b'{"schema": NaN}',
        }
        for name, data in cases.items():
            with self.subTest(name):
                put(self.project / LOCK, data)
                rc, out = self.verify()
                self.assertEqual(rc, 1, out)
                self.assertIn("[LOCK_INVALID]", out)

    def test_invalid_manifest_structures(self):
        manifest = self.project / SNAP / av.MANIFEST_NAME
        good = json.loads(manifest.read_text(encoding="utf-8"))
        variants = {
            "unsorted": lambda d: d["files"].reverse(),
            "duplicate": lambda d: d["files"].append(dict(d["files"][0])),
            "case duplicate": lambda d: d["files"].append({"path": "version", "sha256": "0" * 64}),
            "traversal": lambda d: d["files"].insert(0, {"path": "../x", "sha256": "0" * 64}),
            "no constitution": lambda d: d.update(files=[f for f in d["files"] if f["path"] != "CONSTITUTION.md"]),
            "bad alg": lambda d: d.update(hash_algorithm="md5"),
            "bad canon": lambda d: d.update(canonicalization="raw"),
            "self listed": lambda d: d["files"].append({"path": "ases-manifest.json", "sha256": "0" * 64}),
        }
        for name, fn in variants.items():
            with self.subTest(name):
                data = json.loads(json.dumps(good))
                fn(data)
                raw = (json.dumps(data, indent=2) + "\n").encode("utf-8")
                put(manifest, raw)
                self.write_lock(lambda d, raw=raw: d["manifest"].update(
                    sha256=av.sha256_hex(av.canonical_text_bytes(raw))))
                rc, out = self.verify()
                self.assertEqual(rc, 1, out)
                self.assertIn("[MANIFEST_INVALID]", out)

    def test_unsafe_path_reasons(self):
        for bad in ("", "/a", "a/../b", "a//b", "./a", "a\\b", "C:/a", "a/CON", "a/b.", "a/.git/x", "a/é", "a/b?"):
            self.assertIsNotNone(av.unsafe_path_reason(bad), bad)
        for good in ("docs/governance/ases", "enforcement/cursor/ases.mdc", "VERSION"):
            self.assertIsNone(av.unsafe_path_reason(good), good)


class ApprovalRecord(Base):
    def rewrite(self, **overrides):
        put(self.project / RECORD, record_text(self.lock["manifest"]["sha256"], self.lock["ases_version"],
                                               **overrides))

    def test_record_missing(self):
        os.remove(self.project / RECORD)
        self.assertFails("APPROVAL_RECORD_INVALID")

    def test_record_not_approved(self):
        for decision in ("Pending", "Rejected", "Deferred"):
            self.rewrite(founder_decision=decision)
            self.assertFails("APPROVAL_RECORD_INVALID")

    def test_record_mismatch_and_placeholders(self):
        self.rewrite(to_manifest_sha256="1" * 64)
        self.assertFails("APPROVAL_RECORD_INVALID")
        self.rewrite(to_version="9.9.9")
        self.assertFails("APPROVAL_RECORD_INVALID")
        self.rewrite(evidence="<fill in>")
        self.assertFails("APPROVAL_RECORD_INVALID")
        self.rewrite(founder_approval_date="2026-13-40")
        self.assertFails("APPROVAL_RECORD_INVALID")

    def test_upgrade_requires_diff_review(self):
        self.rewrite(from_version="0.9.0", diff_reviewed="not-applicable")
        self.assertFails("APPROVAL_RECORD_INVALID")
        self.rewrite(from_version="0.9.0", diff_reviewed="yes", change_request="CR-1")
        self.assertEqual(self.verify()[0], 0)

    def test_first_adoption_requires_no_change_request(self):
        self.rewrite(change_request="CR-1")
        self.assertFails("APPROVAL_RECORD_INVALID")

    def test_upgrade_requires_change_request(self):
        self.rewrite(from_version="0.9.0", diff_reviewed="yes", change_request="none")
        self.assertFails("APPROVAL_RECORD_INVALID")

    def test_transition_must_change_version(self):
        self.rewrite(from_version=self.lock["ases_version"], diff_reviewed="yes",
                     change_request="CR-1")
        self.assertFails("APPROVAL_RECORD_INVALID")

    def test_evidence_cannot_be_self_authorization(self):
        for evidence in ("self", "agent", "none", "implied", "silence"):
            self.rewrite(evidence=evidence)
            self.assertFails("APPROVAL_RECORD_INVALID")

    def test_record_malformed(self):
        put(self.project / RECORD, "no front matter\n")
        self.assertFails("APPROVAL_RECORD_INVALID")
        text = record_text(self.lock["manifest"]["sha256"], self.lock["ases_version"])
        put(self.project / RECORD, text.replace("---\n\n#", "founder_decision: Approved\n---\n\n#"))
        self.assertFails("APPROVAL_RECORD_INVALID")

    def test_template_itself_does_not_pass(self):
        shutil.copyfile(str(ROOT / "templates" / "ASES_APPROVAL_RECORD.md"), str(self.project / RECORD))
        self.assertFails("APPROVAL_RECORD_INVALID")


class LockGeneration(Base):
    def run_lock(self, *extra):
        proc = subprocess.run([sys.executable, "-I", str(SCRIPT), "lock", "--project-root", str(self.project)]
                              + list(extra), capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def rewrite(self, **overrides):
        put(self.project / RECORD, record_text(self.lock["manifest"]["sha256"], self.lock["ases_version"],
                                               **overrides))

    def assertRefused(self, record=RECORD):
        before = tree_state(self.project)
        rc, out, err = self.run_lock("--approval-record", record)
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(out, "", "a refused lock must print nothing to stdout")
        self.assertIn("LOCK REFUSED", err)
        self.assertEqual(before, tree_state(self.project), "lock generation must stay read-only")

    def test_valid_record_prints_lock(self):
        rc, out, err = self.run_lock("--approval-record", RECORD)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), self.lock)

    def test_refuses_missing_or_unsafe_record(self):
        self.assertRefused("docs/governance/ases-approvals/nope.md")
        self.assertRefused("../outside.md")
        self.assertRefused(SNAP + "/CONSTITUTION.md")  # a managed file is not an approval record

    def test_refuses_record_not_approved(self):
        for decision in ("Pending", "Rejected", "Deferred"):
            self.rewrite(founder_decision=decision)
            self.assertRefused()

    def test_refuses_record_not_matching_snapshot(self):
        self.rewrite(to_manifest_sha256="1" * 64)
        self.assertRefused()
        self.rewrite(to_version="9.9.9")
        self.assertRefused()

    def test_refuses_malformed_or_template_record(self):
        put(self.project / RECORD, "no front matter\n")
        self.assertRefused()
        shutil.copyfile(str(ROOT / "templates" / "ASES_APPROVAL_RECORD.md"), str(self.project / RECORD))
        self.assertRefused()
        self.rewrite(evidence="<fill in>")
        self.assertRefused()

    def test_record_must_be_given(self):
        rc, out, err = self.run_lock()
        self.assertEqual(rc, 2, out + err)

    def test_manifest_sha256_helper(self):
        before = tree_state(self.project)
        rc, out, err = self.run_lock("--manifest-sha256")
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, self.lock["manifest"]["sha256"] + "\n")
        self.assertEqual(before, tree_state(self.project))

    def test_lock_refuses_tampered_snapshot(self):
        path = self.project / SNAP / "CONSTITUTION.md"
        path.write_bytes(path.read_bytes() + b"tampered\n")
        before = tree_state(self.project)
        rc, out, err = self.run_lock("--approval-record", RECORD)
        self.assertEqual(rc, 1, out + err)
        self.assertEqual(out, "", "a refused lock must print nothing to stdout")
        self.assertIn("LOCK REFUSED", err)
        self.assertIn("snapshot does not verify", err)
        self.assertEqual(before, tree_state(self.project))


class ReadOnlyAndOffline(Base):
    def add_instruction_files(self):
        files = {"AGENTS.md": "project agents rules\n", "CLAUDE.md": "project claude rules\r\n",
                 ".cursor/rules/own.mdc": "own cursor rule\n", ".github/copilot-instructions.md": "own copilot\n",
                 "docs/governance/APPROVED_DECISIONS.md": "decisions\n"}
        for rel, text in files.items():
            put(self.project / rel, text)
        return files

    def test_project_owned_files_unchanged_by_all_commands(self):
        files = self.add_instruction_files()
        before = tree_state(self.project)
        proposed = self.dir / "proposed"
        copy_release(proposed)
        cli("verify", "--project-root", self.project)
        cli("lock", "--project-root", self.project, "--approval-record", RECORD)
        cli("diff", "--project-root", self.project, "--proposed", proposed)
        cli("manifest", "--source-root", ROOT)
        self.assertEqual(before, tree_state(self.project))
        for rel, text in files.items():
            self.assertEqual((self.project / rel).read_bytes(), text.encode("utf-8"))

    def test_verify_never_modifies_on_pass_or_fail(self):
        self.assertEqual(self.verify()[0], 0)
        before = tree_state(self.project)
        self.assertEqual(self.verify()[0], 0)
        self.assertEqual(before, tree_state(self.project))
        path = self.project / SNAP / "CONSTITUTION.md"
        path.write_bytes(path.read_bytes() + b"x\n")
        put(self.project / SNAP / "stray.md", "stray\n")
        os.remove(self.project / SNAP / "VERSION")
        before = tree_state(self.project)
        self.assertEqual(self.verify()[0], 1)
        self.assertEqual(before, tree_state(self.project))

    def test_verify_works_with_network_blocked(self):
        code = (
            "import socket, runpy, sys\n"
            "def blocked(*a, **k):\n    raise RuntimeError('network access attempted')\n"
            "socket.socket = blocked; socket.create_connection = blocked; socket.getaddrinfo = blocked\n"
            "sys.argv = [%r, 'verify', '--project-root', %r]\n"
            "runpy.run_path(%r, run_name='__main__')\n" % (str(SCRIPT), str(self.project), str(SCRIPT)))
        proc = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

    def test_verifier_source_is_read_only_and_offline_by_construction(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported, {"argparse", "collections", "datetime", "difflib", "hashlib", "json",
                                        "os", "re", "sys"})
        banned_calls = {"remove", "unlink", "rename", "rmdir", "makedirs", "mkdir", "write_text",
                        "write_bytes", "copy", "copyfile", "move", "rmtree", "symlink", "chmod", "system",
                        "popen", "urlopen"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                self.assertNotIn(name, banned_calls)
                if name == "replace" and isinstance(node.func, ast.Attribute):
                    self.assertNotEqual(getattr(node.func.value, "id", ""), "os", "os.replace is a write")
                if name == "open":
                    modes = [a.value for a in node.args[1:2] if isinstance(a, ast.Constant)]
                    self.assertTrue(all(m == "rb" for m in modes) and modes, "open() must be rb only")


class DiffAndCli(Base):
    def proposed(self, tweak=None):
        proposed = self.dir / "proposed"
        copy_release(proposed)
        if tweak:
            tweak(proposed)
            put(proposed / av.MANIFEST_NAME, av.dump_json(av.build_manifest(av.real_root(str(proposed)))))
        return proposed

    def test_diff_reports_changes(self):
        def tweak(p):
            put(p / "CHANGELOG.md", (p / "CHANGELOG.md").read_bytes() + b"## 9.9.9\n")
            put(p / "CONSTITUTION.md", (p / "CONSTITUTION.md").read_bytes() + b"New article.\n")
        rc, out = cli("diff", "--project-root", self.project, "--proposed", self.proposed(tweak))
        self.assertEqual(rc, 0, out)
        for needle in ("CHANGED CHANGELOG.md", "CHANGED CONSTITUTION.md", "+## 9.9.9", "+New article.",
                       "NOTICE: CONSTITUTION.md changed", "does not approve"):
            self.assertIn(needle, out)

    def test_diff_identical_release(self):
        rc, out = cli("diff", "--project-root", self.project, "--proposed", self.proposed())
        self.assertEqual(rc, 0, out)
        self.assertIn("No content differences", out)

    def test_diff_refuses_tampered_proposal_or_baseline(self):
        proposed = self.proposed()
        put(proposed / "CHANGELOG.md", (proposed / "CHANGELOG.md").read_bytes() + b"x\n")
        rc, out = cli("diff", "--project-root", self.project, "--proposed", proposed)
        self.assertEqual(rc, 1, out)
        self.assertIn("REFUSED", out)
        os.remove(self.project / SNAP / "VERSION")
        rc, out = cli("diff", "--project-root", self.project, "--proposed", self.proposed())
        self.assertEqual(rc, 1, out)
        self.assertIn("REFUSED", out)

    def test_diff_refuses_proposed_version_file_vs_manifest_mismatch(self):
        """File hashes are all valid, but VERSION disagrees with manifest.ases_version: fail closed."""
        def tweak(p):
            put(p / "VERSION", "9.9.9\n")
        proposed = self.proposed(tweak)  # consistent: manifest says 9.9.9 and VERSION says 9.9.9
        rc, out = cli("diff", "--project-root", self.project, "--proposed", proposed)
        self.assertEqual(rc, 0, out)
        manifest = proposed / av.MANIFEST_NAME
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["ases_version"] = "1.0.0"  # VERSION file still hashes correctly, but now disagrees
        put(manifest, json.dumps(data, indent=2) + "\n")
        self.assertEqual(av.check_snapshot(av.real_root(str(proposed)), data, False)[0], [])
        rc, out = cli("diff", "--project-root", self.project, "--proposed", proposed)
        self.assertEqual(rc, 1, out)
        self.assertIn("REFUSED", out)
        self.assertIn("[VERSION_MISMATCH] proposed VERSION", out)
        self.assertNotIn("CHANGED", out)

    def test_usage_and_io_errors_fail_closed(self):
        self.assertEqual(cli()[0], 2)
        self.assertEqual(cli("verify", "--project-root", self.dir / "does-not-exist")[0], 2)
        self.assertEqual(cli("lock", "--project-root", self.project, "--approval-record", RECORD,
                             "--source-commit", "xyz")[0], 2)


if __name__ == "__main__":
    unittest.main()
