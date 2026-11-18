#!/usr/bin/env python3
"""ASES UAM verifier: offline, read-only, Python standard library only.

Subcommands (none of them ever writes a file; output goes to stdout):
  verify    Check an adopted project's ASES snapshot against its lock.
  diff      Show differences between the installed and a proposed ASES release.
  lock      Print a lock document for an already-vendored snapshot.
  manifest  Print (or --check) the manifest of an ASES source checkout.

Exit codes: 0 = pass, 1 = verification failed, 2 = usage error or integrity
could not be established (fail closed). See docs/UAM.md.

This tool checks integrity and consistency only. It cannot prove that the
Founder approved anything, and it cannot prove that an AI agent obeys any
instruction file.
"""
import argparse
import collections
import datetime
import difflib
import hashlib
import json
import os
import re
import sys

MANIFEST_NAME = "ases-manifest.json"
MANIFEST_SCHEMA = "ases-manifest/1"
LOCK_SCHEMA = "ases-lock/1"
APPROVAL_SCHEMA = "ases-approval/1"
CANONICALIZATION = "text-lf-v1"
HASH_ALGORITHM = "sha256"
DEFAULT_LOCK = "docs/governance/ases.lock.json"
DEFAULT_SNAPSHOT_DIR = "docs/governance/ases"
DEFAULT_REPOSITORY = "https://github.com/tieucaca2004/AI-Software-Engineering-Standard"

# The exact set of files that form the ASES-managed snapshot. Used only by the
# `manifest` subcommand (source side). A project verifies against the manifest
# it vendored, never against this list.
MANAGED_FILES = (
    "AGENTS.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "CONSTITUTION.md",
    "VERSION",
    "docs/ENFORCEMENT_MODEL.md",
    "docs/PROJECT_ADOPTION.md",
    "docs/UAM.md",
    "enforcement/copilot-instructions.md",
    "enforcement/cursor/ases.mdc",
    "enforcement/generic/PROJECT_AI_INSTRUCTIONS.md",
    "scripts/ases_verify.py",
    "templates/ASES_APPROVAL_RECORD.md",
    "templates/CHANGE_REQUEST.md",
)
REQUIRED_IN_MANIFEST = ("CONSTITUTION.md", "VERSION")

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2

SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GITSHA = re.compile(r"^[0-9a-f]{40}$")
RESERVED = {"CON", "PRN", "AUX", "NUL", "CLOCK$"} | {"COM%d" % i for i in range(1, 10)} | {
    "LPT%d" % i for i in range(1, 10)}

Finding = collections.namedtuple("Finding", "code subject message")
Result = collections.namedtuple("Result", "findings verified declared lock manifest base")

HINTS = {
    "LOCK_MISSING": "Project is not adopted (or lock path is wrong). See docs/PROJECT_ADOPTION.md.",
    "LOCK_INVALID": "Fix the lock structure (see docs/UAM.md). Do not hand-edit hashes to make it pass.",
    "MANIFEST_INVALID": "The vendored manifest is malformed. Re-vendor it from the approved ASES release.",
    "MANIFEST_MISMATCH": "Manifest differs from the one the lock was created for. Restore it from Git "
                         "or follow the upgrade-approval process.",
    "VERSION_MISMATCH": "Lock, manifest and snapshot VERSION must agree. Restore from Git or re-adopt "
                        "through the approval process.",
    "FILE_MISSING": "Restore the file from Git history or re-vendor the approved release.",
    "FILE_MODIFIED": "Managed files must not be edited in the project. Restore from Git, or record a "
                     "Founder-approved exception outside the snapshot.",
    "FILE_UNEXPECTED": "Move project files out of the snapshot directory, or remove the stray entry.",
    "FILE_INVALID": "Managed entries must be regular files inside the snapshot (no links).",
    "APPROVAL_RECORD_INVALID": "Create/complete the approval record from templates/ASES_APPROVAL_RECORD.md "
                               "only after an explicit Founder decision.",
}


class PathProblem(Exception):
    pass


# ----------------------------------------------------------------- hashing
def canonical_text_bytes(data):
    """text-lf-v1: valid UTF-8 text, CRLF -> LF. Anything ambiguous is rejected."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is not allowed")
    if b"\x00" in data:
        raise ValueError("NUL byte (binary or UTF-16 content)")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("not valid UTF-8")
    out = data.replace(b"\r\n", b"\n")
    if b"\r" in out:
        raise ValueError("lone carriage return (ambiguous line ending)")
    return out


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def file_hash(path):
    return sha256_hex(canonical_text_bytes(read_bytes(path)))


# ------------------------------------------------------------------- paths
def unsafe_path_reason(path):
    """Return why a project-relative POSIX path is unacceptable, or None."""
    if not isinstance(path, str) or not path:
        return "empty or not a string"
    if len(path) > 200:
        return "path too long"
    if not path.isascii():
        return "non-ASCII characters"
    if any(ord(ch) < 32 or ch in '<>:"|?*\\' for ch in path):
        return "illegal character (control, backslash, colon, wildcard)"
    if path.startswith("/"):
        return "absolute path"
    for part in path.split("/"):
        if part in ("", ".", ".."):
            return "empty, '.' or '..' component"
        if part.endswith((".", " ")):
            return "component ends with dot or space"
        if part.upper().split(".")[0] in RESERVED:
            return "reserved device name"
        if part.lower() == ".git":
            return "'.git' component"
    return None


def _is_junction(path):
    probe = getattr(os.path, "isjunction", None)
    return bool(probe and probe(path))


def real_root(path):
    root = os.path.realpath(path)
    if not os.path.isdir(root):
        raise ValueError("not a directory: %s" % path)
    return root


def resolve_inside(root_real, rel):
    """Join a safe relative path onto the real root; refuse links/escapes."""
    reason = unsafe_path_reason(rel)
    if reason:
        raise PathProblem("unsafe path %r: %s" % (rel, reason))
    parts = rel.split("/")
    current = root_real
    for part in parts:
        current = os.path.join(current, part)
        if not os.path.lexists(current):
            break
        if os.path.islink(current) or _is_junction(current):
            raise PathProblem("%r passes through a symbolic link or junction" % rel)
    full = os.path.join(root_real, *parts)
    if os.path.lexists(full):
        expected = os.path.normcase(os.path.join(root_real, *parts))
        if os.path.normcase(os.path.realpath(full)) != expected:
            raise PathProblem("%r does not resolve inside the project root" % rel)
    return full


def scan_entries(base):
    """Yield (relative_posix_path, kind) for everything under base ('file'|'link')."""
    stack = [(base, "")]
    while stack:
        directory, prefix = stack.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda e: e.name):
                rel = prefix + entry.name
                if entry.is_symlink() or _is_junction(entry.path):
                    yield rel, "link"
                elif entry.is_dir(follow_symlinks=False):
                    stack.append((entry.path, rel + "/"))
                else:
                    yield rel, "file"


# --------------------------------------------------------------- strict JSON
def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key %r" % key)
        out[key] = value
    return out


def _reject_constant(name):
    raise ValueError("invalid JSON constant %s" % name)


def load_json_strict(data):
    text = canonical_text_bytes(data).decode("utf-8")
    return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)


def _exact_keys(obj, keys, where, errors):
    if not isinstance(obj, dict):
        errors.append("%s must be an object" % where)
        return False
    extra, missing = sorted(set(obj) - set(keys)), sorted(set(keys) - set(obj))
    if extra:
        errors.append("%s has unknown key(s): %s" % (where, ", ".join(extra)))
    if missing:
        errors.append("%s is missing key(s): %s" % (where, ", ".join(missing)))
    return not extra and not missing


def _is_str(value):
    return isinstance(value, str) and not any(ord(c) < 32 for c in value)


# -------------------------------------------------------------------- lock
def parse_lock(data):
    errors = []
    try:
        lock = load_json_strict(data)
    except ValueError as exc:
        return None, ["not valid canonical UTF-8 JSON: %s" % exc]
    if not _exact_keys(lock, ("schema", "ases_version", "snapshot_dir", "manifest", "source", "approval"),
                       "lock", errors):
        return None, errors
    if lock["schema"] != LOCK_SCHEMA:
        errors.append("schema must be %r" % LOCK_SCHEMA)
    if not (isinstance(lock["ases_version"], str) and SEMVER.match(lock["ases_version"])):
        errors.append("ases_version must be MAJOR.MINOR.PATCH")
    reason = unsafe_path_reason(lock["snapshot_dir"])
    if reason:
        errors.append("snapshot_dir: %s" % reason)
    if _exact_keys(lock["manifest"], ("sha256",), "manifest", errors):
        if not (isinstance(lock["manifest"]["sha256"], str) and SHA256.match(lock["manifest"]["sha256"])):
            errors.append("manifest.sha256 must be 64 lowercase hex characters")
    if _exact_keys(lock["source"], ("repository", "commit"), "source", errors):
        if not (_is_str(lock["source"]["repository"]) and 0 < len(lock["source"]["repository"]) <= 300):
            errors.append("source.repository must be a non-empty string")
        commit = lock["source"]["commit"]
        if commit is not None and not (isinstance(commit, str) and GITSHA.match(commit)):
            errors.append("source.commit must be null or 40 lowercase hex characters")
    if _exact_keys(lock["approval"], ("record",), "approval", errors):
        reason = unsafe_path_reason(lock["approval"]["record"])
        if reason:
            errors.append("approval.record: %s" % reason)
        elif not errors and lock["approval"]["record"].startswith(lock["snapshot_dir"] + "/"):
            errors.append("approval.record must live outside snapshot_dir (project-owned)")
    return (None, errors) if errors else (lock, [])


def build_lock(root_real, snapshot_dir, repository, commit, record):
    reason = unsafe_path_reason(snapshot_dir)
    if reason:
        raise ValueError("snapshot_dir: %s" % reason)
    full = resolve_inside(root_real, snapshot_dir + "/" + MANIFEST_NAME)
    data = read_bytes(full)
    manifest, errors = parse_manifest(data)
    if errors:
        raise ValueError("vendored manifest invalid: " + "; ".join(errors))
    lock = collections.OrderedDict([
        ("schema", LOCK_SCHEMA),
        ("ases_version", manifest["ases_version"]),
        ("snapshot_dir", snapshot_dir),
        ("manifest", collections.OrderedDict([("sha256", sha256_hex(canonical_text_bytes(data)))])),
        ("source", collections.OrderedDict([("repository", repository), ("commit", commit)])),
        ("approval", collections.OrderedDict([("record", record)])),
    ])
    _, errors = parse_lock(dump_json(lock))
    if errors:
        raise ValueError("generated lock invalid: " + "; ".join(errors))
    return lock


# ---------------------------------------------------------------- manifest
def parse_manifest(data):
    errors = []
    try:
        manifest = load_json_strict(data)
    except ValueError as exc:
        return None, ["not valid canonical UTF-8 JSON: %s" % exc]
    if not _exact_keys(manifest, ("schema", "ases_version", "canonicalization", "hash_algorithm", "files"),
                       "manifest", errors):
        return None, errors
    if manifest["schema"] != MANIFEST_SCHEMA:
        errors.append("schema must be %r" % MANIFEST_SCHEMA)
    if not (isinstance(manifest["ases_version"], str) and SEMVER.match(manifest["ases_version"])):
        errors.append("ases_version must be MAJOR.MINOR.PATCH")
    if manifest["canonicalization"] != CANONICALIZATION:
        errors.append("canonicalization must be %r" % CANONICALIZATION)
    if manifest["hash_algorithm"] != HASH_ALGORITHM:
        errors.append("hash_algorithm must be %r" % HASH_ALGORITHM)
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        errors.append("files must be a non-empty list")
        return None, errors
    paths, folded = [], set()
    for index, entry in enumerate(files):
        where = "files[%d]" % index
        if not _exact_keys(entry, ("path", "sha256"), where, errors):
            continue
        reason = unsafe_path_reason(entry["path"])
        if reason:
            errors.append("%s.path: %s" % (where, reason))
            continue
        if not (isinstance(entry["sha256"], str) and SHA256.match(entry["sha256"])):
            errors.append("%s.sha256 must be 64 lowercase hex characters" % where)
        if entry["path"].lower() in folded:
            errors.append("%s.path duplicates another entry (case-insensitive): %s" % (where, entry["path"]))
        folded.add(entry["path"].lower())
        paths.append(entry["path"])
    if paths != sorted(paths):
        errors.append("files must be sorted by path")
    if MANIFEST_NAME in folded:
        errors.append("manifest must not list itself")
    for required in REQUIRED_IN_MANIFEST:
        if required not in paths:
            errors.append("manifest must list %s" % required)
    return (None, errors) if errors else (manifest, [])


def build_manifest(source_root):
    entries = []
    for rel in sorted(MANAGED_FILES):
        full = resolve_inside(source_root, rel)
        if not os.path.isfile(full):
            raise ValueError("managed file missing: %s" % rel)
        try:
            entries.append(collections.OrderedDict([("path", rel), ("sha256", file_hash(full))]))
        except ValueError as exc:
            raise ValueError("%s: %s" % (rel, exc))
    version = canonical_text_bytes(read_bytes(resolve_inside(source_root, "VERSION"))).decode("utf-8")
    version = version.rstrip("\n")
    if not SEMVER.match(version):
        raise ValueError("VERSION must contain exactly MAJOR.MINOR.PATCH")
    return collections.OrderedDict([
        ("schema", MANIFEST_SCHEMA),
        ("ases_version", version),
        ("canonicalization", CANONICALIZATION),
        ("hash_algorithm", HASH_ALGORITHM),
        ("files", entries),
    ])


def dump_json(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def check_snapshot(base, manifest, check_unexpected):
    """Compare files under base with the manifest. Returns (findings, ok_count)."""
    findings, ok, expected = [], 0, set()
    for entry in manifest["files"]:
        rel = entry["path"]
        expected.add(rel)
        try:
            full = resolve_inside(base, rel)
        except PathProblem as exc:
            findings.append(Finding("FILE_INVALID", rel, str(exc)))
            continue
        if not os.path.lexists(full):
            findings.append(Finding("FILE_MISSING", rel, "managed file is missing"))
        elif not os.path.isfile(full):
            findings.append(Finding("FILE_INVALID", rel, "not a regular file"))
        else:
            try:
                actual = file_hash(full)
            except ValueError as exc:
                findings.append(Finding("FILE_MODIFIED", rel, "content is not canonical text: %s" % exc))
                continue
            if actual != entry["sha256"]:
                findings.append(Finding("FILE_MODIFIED", rel, "sha256 %s != manifest %s" % (actual, entry["sha256"])))
            else:
                ok += 1
    if check_unexpected:
        for rel, kind in scan_entries(base):
            if rel != MANIFEST_NAME and rel not in expected:
                what = "link" if kind == "link" else "file"
                findings.append(Finding("FILE_UNEXPECTED", rel, "%s inside the snapshot but not listed in the manifest" % what))
    return findings, ok


# ---------------------------------------------------------- approval record
APPROVAL_KEYS = ("record_schema", "from_version", "to_version", "to_manifest_sha256", "change_request",
                 "diff_reviewed", "founder_decision", "founder_approval_date", "evidence")
_LINE = re.compile(r"^([a-z0-9_]+): (.+)$")


def parse_approval_record(data):
    try:
        text = canonical_text_bytes(data).decode("utf-8")
    except ValueError as exc:
        return None, ["not canonical UTF-8 text: %s" % exc]
    lines = text.split("\n")
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return None, ["record must start with a '---' front-matter block closed by '---'"]
    fields, errors = {}, []
    for line in lines[1:lines.index("---", 1)]:
        if not line.strip():
            continue
        match = _LINE.match(line)
        if not match:
            errors.append("malformed line: %r" % line)
        elif match.group(1) in fields:
            errors.append("duplicate field %s" % match.group(1))
        else:
            fields[match.group(1)] = match.group(2).strip()
    if errors:
        return None, errors
    extra, missing = sorted(set(fields) - set(APPROVAL_KEYS)), sorted(set(APPROVAL_KEYS) - set(fields))
    if extra:
        errors.append("unknown field(s): %s" % ", ".join(extra))
    if missing:
        errors.append("missing field(s): %s" % ", ".join(missing))
    if errors:
        return None, errors
    for key, value in fields.items():
        if value.startswith("<") and value.endswith(">"):
            errors.append("%s still contains template placeholder text" % key)
    if fields["record_schema"] != APPROVAL_SCHEMA:
        errors.append("record_schema must be %r" % APPROVAL_SCHEMA)
    if fields["from_version"] != "none" and not SEMVER.match(fields["from_version"]):
        errors.append("from_version must be 'none' or MAJOR.MINOR.PATCH")
    if not SEMVER.match(fields["to_version"]):
        errors.append("to_version must be MAJOR.MINOR.PATCH")
    if not SHA256.match(fields["to_manifest_sha256"]):
        errors.append("to_manifest_sha256 must be 64 lowercase hex characters")
    if fields["diff_reviewed"] not in ("yes", "not-applicable"):
        errors.append("diff_reviewed must be 'yes' or 'not-applicable'")
    elif fields["from_version"] != "none" and fields["diff_reviewed"] != "yes":
        errors.append("an upgrade/rollback requires diff_reviewed: yes")
    if fields["founder_decision"] != "Approved":
        errors.append("founder_decision is %r; only 'Approved' allows adoption" % fields["founder_decision"])
    try:
        datetime.date.fromisoformat(fields["founder_approval_date"])
    except ValueError:
        errors.append("founder_approval_date must be a valid YYYY-MM-DD date")
    return (None, errors) if errors else (fields, [])


# ------------------------------------------------------------------ verify
def verify_project(root_real, lock_rel, expect_version=None):
    findings, verified, declared = [], [], []

    def done(lock=None, manifest=None, base=None):
        return Result(findings, verified, declared, lock, manifest, base)

    def add(code, subject, message):
        findings.append(Finding(code, subject, message))

    try:
        lock_full = resolve_inside(root_real, lock_rel)
    except PathProblem as exc:
        add("LOCK_INVALID", lock_rel, str(exc))
        return done()
    if not os.path.lexists(lock_full):
        add("LOCK_MISSING", lock_rel, "lock file not found")
        return done()
    if not os.path.isfile(lock_full):
        add("LOCK_INVALID", lock_rel, "not a regular file")
        return done()
    lock, errors = parse_lock(read_bytes(lock_full))
    if errors:
        for message in errors:
            add("LOCK_INVALID", lock_rel, message)
        return done()
    snapshot = lock["snapshot_dir"]
    manifest_rel = snapshot + "/" + MANIFEST_NAME
    try:
        manifest_full = resolve_inside(root_real, manifest_rel)
        base = resolve_inside(root_real, snapshot)
    except PathProblem as exc:
        add("FILE_INVALID", snapshot, str(exc))
        return done(lock)
    if not os.path.isfile(manifest_full):
        add("FILE_MISSING", manifest_rel, "vendored manifest is missing")
        return done(lock)
    manifest_bytes = read_bytes(manifest_full)
    manifest, errors = parse_manifest(manifest_bytes)
    if errors:
        for message in errors:
            add("MANIFEST_INVALID", manifest_rel, message)
        return done(lock)
    manifest_hash = sha256_hex(canonical_text_bytes(manifest_bytes))
    if manifest_hash != lock["manifest"]["sha256"]:
        add("MANIFEST_MISMATCH", manifest_rel,
            "manifest sha256 %s != lock %s" % (manifest_hash, lock["manifest"]["sha256"]))
        return done(lock)
    verified.append("manifest SHA-256 matches the lock (%s)" % manifest_hash)

    if lock["ases_version"] != manifest["ases_version"]:
        add("VERSION_MISMATCH", lock_rel, "lock says %s but manifest says %s" % (
            lock["ases_version"], manifest["ases_version"]))
    if expect_version is not None and expect_version != lock["ases_version"]:
        add("VERSION_MISMATCH", "--expect-version", "expected %s but the lock pins %s" % (
            expect_version, lock["ases_version"]))
    file_findings, ok = check_snapshot(base, manifest, True)
    findings.extend(file_findings)
    try:
        installed = canonical_text_bytes(read_bytes(resolve_inside(base, "VERSION"))).decode("utf-8").rstrip("\n")
        if installed != manifest["ases_version"]:
            add("VERSION_MISMATCH", snapshot + "/VERSION", "snapshot VERSION is %r but manifest says %s" % (
                installed, manifest["ases_version"]))
    except (OSError, ValueError, PathProblem):
        pass  # already reported as missing/modified/invalid above
    if not file_findings:
        verified.append("%d managed file(s) match their manifest SHA-256 (%s); no unexpected files" % (
            ok, CANONICALIZATION))
    if not findings:
        verified.append("ases_version %s agrees across lock, manifest and snapshot VERSION" % lock["ases_version"])

    record_rel = lock["approval"]["record"]
    try:
        record_full = resolve_inside(root_real, record_rel)
        if not os.path.isfile(record_full):
            raise PathProblem("approval record not found")
        fields, errors = parse_approval_record(read_bytes(record_full))
    except PathProblem as exc:
        fields, errors = None, [str(exc)]
    if not errors:
        if fields["to_version"] != lock["ases_version"]:
            errors.append("record to_version %s != lock %s" % (fields["to_version"], lock["ases_version"]))
        if fields["to_manifest_sha256"] != lock["manifest"]["sha256"]:
            errors.append("record to_manifest_sha256 does not match the lock manifest sha256")
    for message in errors:
        add("APPROVAL_RECORD_INVALID", record_rel, message)
    declared.append("source.repository: %s" % lock["source"]["repository"])
    declared.append("source.commit: %s" % (lock["source"]["commit"] or "not recorded"))
    if not errors:
        declared.append("approval record %s: %s -> %s, decision=%s, date=%s, evidence=%s. This tool CANNOT "
                        "verify that the Founder actually made this decision." % (
                            record_rel, fields["from_version"], fields["to_version"],
                            fields["founder_decision"], fields["founder_approval_date"], fields["evidence"]))
    return done(lock, manifest, base)


def print_findings(findings):
    for item in findings:
        print("  [%s] %s: %s" % (item.code, item.subject, item.message))
    for code in sorted({item.code for item in findings}):
        print("  fix %s: %s" % (code, HINTS.get(code, "")))


def cmd_verify(args):
    root = real_root(args.project_root)
    result = verify_project(root, args.lock, args.expect_version)
    print("ASES VERIFY")
    print("Project root: %s" % root)
    print("Lock: %s" % args.lock)
    if result.verified:
        print("VERIFIED (computed here from local files):")
        for line in result.verified:
            print("  - %s" % line)
    if result.declared:
        print("DECLARED (self-reported, not verified):")
        for line in result.declared:
            print("  - %s" % line)
    if result.findings:
        print("FINDINGS:")
        print_findings(result.findings)
        print("RESULT: FAIL (%d finding(s)). Integrity is NOT established." % len(result.findings))
        return EXIT_FAIL
    print("RESULT: PASS (snapshot integrity established; approval is only declared).")
    print("LIMITS: no signatures. Someone who can rewrite both the snapshot and the lock can defeat this "
          "check; rely on protected branches and Founder review for that. It does not prove an AI agent "
          "obeyed any instruction.")
    return EXIT_OK


def cmd_lock(args):
    root = real_root(args.project_root)
    if args.source_commit is not None and not GITSHA.match(args.source_commit):
        raise ValueError("--source-commit must be 40 lowercase hex characters")
    lock = build_lock(root, args.snapshot_dir, args.repository, args.source_commit, args.approval_record)
    sys.stdout.flush()
    sys.stdout.buffer.write(dump_json(lock))
    sys.stdout.buffer.flush()
    return EXIT_OK


def cmd_manifest(args):
    root = real_root(args.source_root)
    data = dump_json(build_manifest(root))
    if args.check:
        path = resolve_inside(root, MANIFEST_NAME)
        if not os.path.isfile(path) or canonical_text_bytes(read_bytes(path)) != data:
            print("ASES MANIFEST: %s is missing or stale. Regenerate it with: "
                  "python scripts/ases_verify.py manifest > %s" % (MANIFEST_NAME, MANIFEST_NAME))
            return EXIT_FAIL
        print("ASES MANIFEST: %s is current (%d managed files)." % (MANIFEST_NAME, len(MANAGED_FILES)))
        return EXIT_OK
    sys.stdout.flush()
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    return EXIT_OK


def _canonical_lines(path):
    return canonical_text_bytes(read_bytes(path)).decode("utf-8").split("\n")


def cmd_diff(args):
    root = real_root(args.project_root)
    installed = verify_project(root, args.lock)
    print("ASES DIFF (read-only review aid; it does not approve anything)")
    if installed.findings:
        print("REFUSED: the installed snapshot does not verify, so it cannot be used as a baseline.")
        print_findings(installed.findings)
        return EXIT_FAIL
    proposed_root = real_root(args.proposed)
    try:
        manifest_full = resolve_inside(proposed_root, MANIFEST_NAME)
        if not os.path.isfile(manifest_full):
            raise PathProblem("no %s in proposed release" % MANIFEST_NAME)
        proposed, errors = parse_manifest(read_bytes(manifest_full))
    except PathProblem as exc:
        proposed, errors = None, [str(exc)]
    if errors:
        print("REFUSED: proposed manifest invalid: " + "; ".join(errors))
        return EXIT_FAIL
    findings, _ = check_snapshot(proposed_root, proposed, False)
    if findings:
        print("REFUSED: the proposed release does not match its own manifest.")
        print_findings(findings)
        return EXIT_FAIL
    old = {e["path"]: e["sha256"] for e in installed.manifest["files"]}
    new = {e["path"]: e["sha256"] for e in proposed["files"]}
    proposed_hash = sha256_hex(canonical_text_bytes(read_bytes(manifest_full)))
    print("Installed: ASES %s (manifest %s)" % (installed.lock["ases_version"], installed.lock["manifest"]["sha256"]))
    print("Proposed : ASES %s (manifest %s)" % (proposed["ases_version"], proposed_hash))
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    changed = sorted(p for p in set(old) & set(new) if old[p] != new[p])
    print("Added: %d  Removed: %d  Changed: %d  Unchanged: %d" % (
        len(added), len(removed), len(changed), len(set(old) & set(new)) - len(changed)))
    for path in added:
        print("ADDED   %s" % path)
    for path in removed:
        print("REMOVED %s" % path)
    for path in changed:
        print("CHANGED %s" % path)
    if "CONSTITUTION.md" in changed:
        print("NOTICE: CONSTITUTION.md changed. A Constitution amendment needs explicit Founder approval.")
    if not (added or removed or changed):
        print("No content differences.")
    if not args.names_only:
        for path in changed:
            old_lines = _canonical_lines(resolve_inside(installed.base, path))
            new_lines = _canonical_lines(resolve_inside(proposed_root, path))
            for line in difflib.unified_diff(old_lines, new_lines, "installed/" + path, "proposed/" + path,
                                             lineterm="", n=3):
                print(line)
    print("NEXT: Founder reviews this diff, then explicitly decides. Record the decision with "
          "templates/ASES_APPROVAL_RECORD.md. Do not change the snapshot or lock before that decision.")
    return EXIT_OK


# --------------------------------------------------------------------- CLI
def build_parser():
    parser = argparse.ArgumentParser(prog="ases_verify.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify", help="verify an adopted project (read-only, offline)")
    p.add_argument("--project-root", default=".")
    p.add_argument("--lock", default=DEFAULT_LOCK, help="lock path relative to the project root")
    p.add_argument("--expect-version", help="fail unless the lock pins exactly this version")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("diff", help="show installed vs proposed ASES release (read-only)")
    p.add_argument("--project-root", default=".")
    p.add_argument("--lock", default=DEFAULT_LOCK)
    p.add_argument("--proposed", required=True, help="local directory holding the proposed ASES release")
    p.add_argument("--names-only", action="store_true", help="list changed files without text diffs")
    p.set_defaults(func=cmd_diff)
    p = sub.add_parser("lock", help="print a lock document for a vendored snapshot")
    p.add_argument("--project-root", default=".")
    p.add_argument("--snapshot-dir", default=DEFAULT_SNAPSHOT_DIR)
    p.add_argument("--repository", default=DEFAULT_REPOSITORY)
    p.add_argument("--source-commit", help="40-hex ASES commit the snapshot was taken from (declared)")
    p.add_argument("--approval-record", required=True, help="project-relative path of the approval record")
    p.set_defaults(func=cmd_lock)
    p = sub.add_parser("manifest", help="print (or --check) the manifest of an ASES source checkout")
    p.add_argument("--source-root", default=".")
    p.add_argument("--check", action="store_true", help="exit 1 if the committed manifest is stale")
    p.set_defaults(func=cmd_manifest)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # fail closed: never report success on an unexpected error
        print("ERROR (fail closed): %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
