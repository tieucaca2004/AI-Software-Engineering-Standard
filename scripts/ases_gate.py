#!/usr/bin/env python3
"""ASES task-entry governance gate: offline, read-only, standard library only.

It answers one question before implementation starts: does this repository have
a complete project context, an explicitly authorized current task, and (when
adopted) an intact ASES snapshot?

It does not prove that an agent read a document, and it cannot prove that a
Founder approval is genuine. It makes missing or incomplete governance visible
and blocks the supported workflow until the responsible person fixes it.

Exit codes: 0 = pass, 1 = blocked, 2 = usage error or the check could not run.
"""
import argparse
import collections
import datetime
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ases_identity  # noqa: E402
import ases_verify as av  # noqa: E402

DEFAULT_CONTEXT = "docs/governance/PROJECT_CONTEXT.md"
DEFAULT_TASK = "docs/governance/CURRENT_TASK.md"
DEFAULT_LOCK = "docs/governance/ases.lock.json"
DEFAULT_SNAPSHOT_DIR = "docs/governance/ases"
DEFAULT_CONSTITUTION = "CONSTITUTION.md"

EXIT_OK, EXIT_BLOCKED, EXIT_ERROR = 0, 1, 2

Finding = collections.namedtuple("Finding", "code subject message")

HINTS = {
    "CONSTITUTION_MISSING": "Add the governing CONSTITUTION.md, or adopt ASES with a lock.",
    "SNAPSHOT_LOCK_MISSING": "The snapshot exists but no lock does. Follow docs/PROJECT_ADOPTION.md.",
    "SNAPSHOT_INVALID": "Fix the ASES snapshot/lock/approval findings before doing project work.",
    "CONTEXT_MISSING": "Create docs/governance/PROJECT_CONTEXT.md from templates/PROJECT_CONTEXT.md.",
    "CONTEXT_INVALID": "Make the context valid UTF-8 Markdown without BOM, NUL or lone CR characters.",
    "CONTEXT_SECTION_MISSING": "Add the required section to the project context.",
    "CONTEXT_SECTION_EMPTY": "Fill the section with project-specific facts, not placeholders.",
    "CONTEXT_FIELD_MISSING": "Add the required field to the project context.",
    "CONTEXT_FIELD_DUPLICATE": "Keep exactly one value for each required field.",
    "CONTEXT_FIELD_INVALID": "Provide a substantive value; placeholders and bare TBD/N/A are not enough.",
    "CONTEXT_PLACEHOLDER": "Replace every placeholder before implementation.",
    "CONTEXT_REQUIREMENTS": "Add a complete requirements table with acceptance criteria and status.",
    "CONTEXT_SCOPE": "Record at least one in-scope and one out-of-scope item.",
    "CONTEXT_MILESTONE": "Record the current milestone, objective, authorized scope and acceptance criteria.",
    "CONTEXT_DECISIONS": "Point to the approved decisions record; do not invent approval.",
    "TASK_MISSING": "Create docs/governance/CURRENT_TASK.md from templates/CURRENT_TASK.md.",
    "TASK_INVALID": "Make the task valid UTF-8 Markdown without BOM, NUL or lone CR characters.",
    "TASK_FIELD_MISSING": "Add the required task authorization field.",
    "TASK_FIELD_DUPLICATE": "Keep exactly one value for each task field.",
    "TASK_FIELD_INVALID": "Provide a substantive, authorized value.",
    "TASK_NOT_AUTHORIZED": "Only Status: Authorized permits implementation. Do not self-authorize.",
    "TASK_PROJECT_MISMATCH": "The task must name the same project as the project context.",
    "TASK_PLACEHOLDER": "Replace every task placeholder before implementation.",
    "TASK_CHANGED_FILES_MISSING": "Supply --baseline, --changed-files, or --legacy-collect before scope enforcement.",
    "TASK_CHANGED_FILES_INVALID": "Changed-file paths must be project-relative, with no '..' or drive prefix.",
    "TASK_SCOPE_VIOLATION": "The changed path is outside Files/modules allowed. Stop or obtain a new task authorization.",
    "TASK_BASELINE_MISSING": "Capture a per-work-unit baseline with 'ases_gate.py baseline' before execution.",
    "TASK_BASELINE_INVALID": "Provide a valid, uncorrupted baseline that matches this repository and work unit.",
    "IDENTITY_INVALID": "Fix or provide a valid task-identity record; see templates/TASK_IDENTITY.json and docs/IDENTITY_CONTRACT.md.",
}

REQUIRED_SECTIONS = (
    "project identity",
    "business problem and users",
    "scope",
    "requirements",
    "architecture and data",
    "security and quality",
    "delivery plan",
    "current milestone",
    "founder decisions",
)

IDENTITY_FIELDS = ("Project name", "Project ID", "Repository", "Primary branch", "Owner")
ARCHITECTURE_FIELDS = ("Data storage", "API/integration", "Authentication/authorization",
                       "Error handling", "Deployment", "Backup/recovery")
SECURITY_FIELDS = ("Secrets", "Permissions", "Input validation", "Audit logging")
DELIVERY_FIELDS = ("Milestones", "Test strategy", "Risks")
MILESTONE_FIELDS = ("Milestone ID", "Objective", "Authorized scope", "Acceptance criteria", "Status")
TASK_FIELDS = (
    "Task ID", "Project", "Agent", "Requested by", "Date", "Status", "Objective",
    "Authorized scope", "Files/modules allowed", "Prohibited actions",
    "Implementation requirements", "Testing requirements", "Acceptance criteria",
    "Approved decisions reference", "Authorization evidence",
)

ALLOWED_TYPES = {
    "functional", "non-functional", "nonfunctional", "business rule", "data",
    "integration", "security", "performance", "reliability", "compliance",
}
ALLOWED_REQUIREMENT_STATUS = {
    "proposed", "specified", "approved", "implemented", "tested", "verified",
    "accepted", "deferred",
}
ALLOWED_MILESTONE_STATUS = {"planned", "in progress"}

PLACEHOLDER = re.compile(r"<[^<>\n]{1,200}>|\b(?:TBD|TBC|TODO|FIXME)\b", re.IGNORECASE)
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEADING2 = re.compile(r"^##\s+(.+?)\s*$")
HEADING3 = re.compile(r"^###\s+(.+?)\s*$")
BULLET = re.compile(r"^[ \t]*[-*][ \t]+(.+?)[ \t]*$", re.MULTILINE)


def structured(value):
    """True when a value carries project-specific content rather than a placeholder."""
    text = value.strip()
    if not text or PLACEHOLDER.search(text):
        return False
    if text.lower() in {"n/a", "na", "none", "tbd", "todo", "fixme", "-", "pending"}:
        return False
    return True


def optional_na(value):
    """Architecture/security fields may be N/A only when a reason is supplied."""
    text = value.strip()
    if not text or PLACEHOLDER.search(text):
        return False
    if text.lower() in {"n/a", "na", "none", "tbd", "todo", "fixme", "-", "pending"}:
        return False
    return True


def read_text(root_real, rel):
    full = av.resolve_inside(root_real, rel)
    if not os.path.isfile(full):
        raise FileNotFoundError(rel)
    return av.canonical_text_bytes(av.read_bytes(full)).decode("utf-8")


def normalize_heading(title):
    title = re.sub(r"^\d+\.\s*", "", title.strip())
    return re.sub(r"\s+", " ", title).strip().lower()


def parse_sections(text):
    sections = {}
    current = None
    for line in text.split("\n"):
        match = HEADING2.match(line)
        if match:
            current = normalize_heading(match.group(1))
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def subsection(section_text, title):
    lines = section_text.split("\n")
    wanted = title.strip().lower()
    out, active = [], False
    for line in lines:
        match = HEADING3.match(line)
        if match:
            active = match.group(1).strip().lower() == wanted
            continue
        if active:
            out.append(line)
    return "\n".join(out).strip()


def field_values(text, name):
    pattern = re.compile(
        r"^\s*(?:[-*]\s*)?%s\s*:\s*(.+?)\s*$" % re.escape(name),
        re.IGNORECASE | re.MULTILINE,
    )
    return [match.group(1).strip() for match in pattern.finditer(text)]


def require_field(text, name, subject, findings, allow_na=False):
    values = field_values(text, name)
    if not values:
        findings.append(Finding("CONTEXT_FIELD_MISSING", subject, "%s is missing" % name))
        return None
    if len(values) > 1:
        findings.append(Finding("CONTEXT_FIELD_DUPLICATE", subject, "%s appears %d times" % (
            name, len(values))))
        return values[0]
    value = values[0]
    valid = optional_na(value) if allow_na else structured(value)
    if not valid:
        findings.append(Finding("CONTEXT_FIELD_INVALID", subject, "%s has no substantive value" % name))
        return None
    return value


def require_bullets(text, subject, findings):
    bullets = [match.group(1) for match in BULLET.finditer(text) if structured(match.group(1))]
    if not bullets:
        findings.append(Finding("CONTEXT_SCOPE", subject, "no substantive bullet item found"))
    return bullets


def check_requirements(section_text, findings):
    rows = []
    malformed = False
    for line in section_text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 5:
            malformed = True
            continue
        if cells[0].lower() == "id":
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    if malformed:
        findings.append(Finding("CONTEXT_REQUIREMENTS", "requirements table",
                                "every row must have exactly 5 columns: ID, Type, Requirement, "
                                "Acceptance criteria, Status"))
    if len(rows) < 2:
        findings.append(Finding("CONTEXT_REQUIREMENTS", "requirements table",
                                "at least two requirements are required"))
        return
    seen_ids = set()
    seen_types = set()
    specified = False
    for cells in rows:
        req_id, req_type, requirement, acceptance, status = cells
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", req_id):
            findings.append(Finding("CONTEXT_REQUIREMENTS", req_id, "invalid requirement ID"))
        if req_id.lower() in seen_ids:
            findings.append(Finding("CONTEXT_REQUIREMENTS", req_id, "duplicate requirement ID"))
        seen_ids.add(req_id.lower())
        req_type_norm = req_type.strip().lower()
        if req_type_norm not in ALLOWED_TYPES:
            findings.append(Finding("CONTEXT_REQUIREMENTS", req_id, "unknown requirement type %r" % req_type))
        seen_types.add(req_type_norm)
        status_norm = status.strip().lower()
        if status_norm not in ALLOWED_REQUIREMENT_STATUS:
            findings.append(Finding("CONTEXT_REQUIREMENTS", req_id, "unknown requirement status %r" % status))
        if status_norm in {"specified", "approved"}:
            specified = True
        if not structured(requirement):
            findings.append(Finding("CONTEXT_REQUIREMENTS", req_id, "requirement text is empty or a placeholder"))
        if not structured(acceptance):
            findings.append(Finding("CONTEXT_REQUIREMENTS", req_id, "acceptance criteria are empty or a placeholder"))
    if "functional" not in seen_types:
        findings.append(Finding("CONTEXT_REQUIREMENTS", "requirements table",
                                "at least one Functional requirement is required"))
    if "non-functional" not in seen_types and "nonfunctional" not in seen_types:
        findings.append(Finding("CONTEXT_REQUIREMENTS", "requirements table",
                                "at least one Non-functional requirement is required"))
    if not specified:
        findings.append(Finding("CONTEXT_REQUIREMENTS", "requirements table",
                                "at least one requirement must be Specified or Approved"))


def check_context(text, root_real, findings):
    if PLACEHOLDER.search(text):
        findings.append(Finding("CONTEXT_PLACEHOLDER", DEFAULT_CONTEXT,
                                "placeholder text is still present"))
    sections = parse_sections(text)
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            findings.append(Finding("CONTEXT_SECTION_MISSING", name, "required section is missing"))
        elif len(sections[name].strip()) < 20:
            findings.append(Finding("CONTEXT_SECTION_EMPTY", name, "required section is empty or too short"))
    if any(name not in sections for name in REQUIRED_SECTIONS):
        return

    identity = sections["project identity"]
    identity_values = {}
    for name in IDENTITY_FIELDS:
        identity_values[name] = require_field(identity, name, "project identity", findings)

    business = sections["business problem and users"]
    if len(business.strip()) < 40:
        findings.append(Finding("CONTEXT_SECTION_EMPTY", "business problem and users",
                                "describe the problem, users and expected outcome"))

    scope = sections["scope"]
    require_bullets(subsection(scope, "In scope"), "scope / In scope", findings)
    require_bullets(subsection(scope, "Out of scope"), "scope / Out of scope", findings)

    check_requirements(sections["requirements"], findings)

    architecture = sections["architecture and data"]
    for name in ARCHITECTURE_FIELDS:
        require_field(architecture, name, "architecture and data", findings, allow_na=True)
    security = sections["security and quality"]
    for name in SECURITY_FIELDS:
        require_field(security, name, "security and quality", findings, allow_na=True)
    delivery = sections["delivery plan"]
    for name in DELIVERY_FIELDS:
        require_field(delivery, name, "delivery plan", findings, allow_na=True)

    milestone = sections["current milestone"]
    milestone_values = {}
    for name in MILESTONE_FIELDS:
        milestone_values[name] = require_field(milestone, name, "current milestone", findings)
    status = milestone_values.get("Status")
    if status is not None and status.strip().lower() not in ALLOWED_MILESTONE_STATUS:
        findings.append(Finding("CONTEXT_MILESTONE", "current milestone",
                                "Status must be Planned or In Progress before implementation, not %r" % status))

    decisions = sections["founder decisions"]
    if "APPROVED_DECISIONS.md" not in decisions:
        findings.append(Finding("CONTEXT_DECISIONS", "founder decisions",
                                "reference docs/governance/APPROVED_DECISIONS.md"))
    else:
        references = field_values(decisions, "Approved decisions")
        if not references:
            findings.append(Finding("CONTEXT_DECISIONS", "founder decisions",
                                    "Approved decisions field is missing"))
        else:
            reference = references[0]
            try:
                decision_file = av.resolve_inside(root_real, reference)
                if not os.path.isfile(decision_file):
                    findings.append(Finding("CONTEXT_DECISIONS", "founder decisions",
                                            "approved decisions file not found: %s" % reference))
                elif os.path.getsize(decision_file) == 0:
                    findings.append(Finding("CONTEXT_DECISIONS", "founder decisions",
                                            "approved decisions file is empty: %s" % reference))
            except av.PathProblem as exc:
                findings.append(Finding("CONTEXT_DECISIONS", "founder decisions",
                                        "unsafe approved decisions path: %s" % exc))
    return identity_values


def check_task(text, context_identity, findings):
    if PLACEHOLDER.search(text):
        findings.append(Finding("TASK_PLACEHOLDER", DEFAULT_TASK, "placeholder text is still present"))
    values = {}
    for name in TASK_FIELDS:
        found = field_values(text, name)
        if not found:
            findings.append(Finding("TASK_FIELD_MISSING", DEFAULT_TASK, "%s is missing" % name))
            continue
        if len(found) > 1:
            findings.append(Finding("TASK_FIELD_DUPLICATE", DEFAULT_TASK, "%s appears %d times" % (
                name, len(found))))
        values[name] = found[0]
        if not structured(found[0]) and not (
                name == "Approved decisions reference" and found[0].strip().lower() == "none"):
            findings.append(Finding("TASK_FIELD_INVALID", DEFAULT_TASK, "%s has no substantive value" % name))

    status = values.get("Status", "")
    if status.strip().lower() != "authorized":
        findings.append(Finding("TASK_NOT_AUTHORIZED", "Status",
                                "Status is %r; only Authorized permits implementation" % status))

    date_value = values.get("Date", "")
    if date_value and not DATE.match(date_value):
        findings.append(Finding("TASK_FIELD_INVALID", "Date", "Date must be YYYY-MM-DD"))
    elif date_value:
        try:
            datetime.date.fromisoformat(date_value)
        except ValueError:
            findings.append(Finding("TASK_FIELD_INVALID", "Date", "Date is not a valid calendar date"))

    if context_identity:
        project_id = (context_identity.get("Project ID") or "").strip().lower()
        project_name = (context_identity.get("Project name") or "").strip().lower()
        task_project = values.get("Project", "").strip().lower()
        if task_project not in {project_id, project_name}:
            findings.append(Finding("TASK_PROJECT_MISMATCH", "Project",
                                    "task project %r does not match context project" % values.get("Project", "")))

    evidence = values.get("Authorization evidence", "").strip()
    if evidence and evidence.lower() in {"self", "agent", "none", "n/a", "implied", "silence"}:
        findings.append(Finding("TASK_FIELD_INVALID", "Authorization evidence",
                                "point to an explicit Founder/authorized-lead decision, not self-authorization"))
    allowed = values.get("Files/modules allowed", "").strip()
    if allowed.lower() in {"none", "n/a", "-"}:
        findings.append(Finding("TASK_FIELD_INVALID", "Files/modules allowed",
                                "list the authorized files or modules, or 'all' for an explicitly repo-wide task"))
    return values


def load_changed_files(root_real, rel, findings):
    """Read a newline-separated changed-file list. Return None when it cannot be used."""
    try:
        text = read_text(root_real, rel)
    except FileNotFoundError:
        findings.append(Finding("TASK_CHANGED_FILES_MISSING", rel, "changed-files list not found"))
        return None
    except (av.PathProblem, OSError, ValueError) as exc:
        findings.append(Finding("TASK_CHANGED_FILES_INVALID", rel, str(exc)))
        return None
    paths = []
    for line in text.split("\n"):
        path = line.strip().replace("\\", "/")
        if not path or path.startswith("#"):
            continue
        parts = path.split("/")
        if (path.startswith("/") or re.match(r"^[A-Za-z]:", path)
                or any(part in ("", ".", "..") for part in parts)
                or any(ord(ch) < 32 for ch in path)):
            findings.append(Finding("TASK_CHANGED_FILES_INVALID", path,
                                    "changed-file path is absolute, empty, '.', '..' or contains control characters"))
            continue
        paths.append(path)
    return paths


def collect_git_changed_files(root, findings):
    """Collect the actual working-tree changed paths (tracked + untracked) from git.

    Used when the caller does not supply --changed-files so scope enforcement is
    not silently skipped for a governed git work unit. Returns None when the
    project root is not a git work tree (scope enforcement does not apply) or when
    collection fails (in which case a finding has been appended and the gate blocks).
    """
    try:
        toplevel = subprocess.run(
            ["git", "-C", root, "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, OSError):
        findings.append(Finding("TASK_CHANGED_FILES_INVALID", "changed files",
                                "git is not available; cannot collect changed files"))
        return None
    if toplevel.returncode != 0:
        return None  # not a git work tree: scope enforcement does not apply here
    top = toplevel.stdout.decode("utf-8", "replace").strip()
    if os.path.normcase(os.path.realpath(top)) != os.path.normcase(os.path.realpath(root)):
        # The project root lives inside an unrelated parent repository, not its own
        # work tree, so git-derived scope enforcement does not apply here.
        return None
    paths = []
    for args in (["git", "-C", root, "diff", "--name-only", "-z", "HEAD"],
                 ["git", "-C", root, "ls-files", "--others", "--exclude-standard", "-z"]):
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            findings.append(Finding("TASK_CHANGED_FILES_INVALID", "changed files",
                                    "git collection failed (%s)" % " ".join(args[2:])))
            return None
        for raw in proc.stdout.split(b"\x00"):
            if not raw:
                continue
            path = raw.decode("utf-8", "replace").replace("\\", "/")
            parts = path.split("/")
            if (path.startswith("/") or re.match(r"^[A-Za-z]:", path)
                    or any(part in ("", ".", "..") for part in parts)
                    or any(ord(ch) < 32 for ch in path)):
                findings.append(Finding("TASK_CHANGED_FILES_INVALID", path,
                                        "changed-file path is absolute, empty, '.', '..' "
                                        "or contains control characters"))
                return None
            paths.append(path)
    return list(dict.fromkeys(paths))


BASELINE_SCHEMA = "ases-baseline/1"


def _is_own_git_root(root):
    """True only when `root` is itself a git work-tree root (not inside a parent repo)."""
    try:
        proc = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (FileNotFoundError, OSError):
        return False
    if proc.returncode != 0:
        return False
    top = proc.stdout.decode("utf-8", "replace").strip()
    return os.path.normcase(os.path.realpath(top)) == os.path.normcase(os.path.realpath(root))


def _raw_sha256(full_path):
    digest = hashlib.sha256()
    with open(full_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _enumerate_snapshot(root):
    """Return {project-relative-path: content_sha256_or_None} for tracked + untracked files.

    Fails closed (raises OSError) when the project root is not its own git work tree,
    so a parent repository discovered by git is never mistaken for the project root.
    """
    if not _is_own_git_root(root):
        raise OSError("project root is not its own git work tree")
    files = {}
    seen = set()
    for extra in (["-z"], ["--others", "--exclude-standard", "-z"]):
        proc = subprocess.run(["git", "-C", root, "ls-files"] + extra,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise OSError("git ls-files failed")
        for raw in proc.stdout.split(b"\x00"):
            if not raw:
                continue
            path = raw.decode("utf-8", "replace").replace("\\", "/")
            if path in seen:
                continue
            seen.add(path)
            full = os.path.join(root, path.replace("/", os.sep))
            files[path] = _raw_sha256(full) if os.path.isfile(full) else None
    return files


def capture_baseline(root, work_unit_id):
    """Capture a working-tree snapshot immediately before a work unit starts."""
    return {
        "schema": BASELINE_SCHEMA,
        "repository_root": os.path.realpath(root),
        "work_unit_id": work_unit_id,
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "files": _enumerate_snapshot(root),
    }


def compute_delta(root, baseline, work_unit_id, findings):
    """Compute the per-work-unit delta against a baseline snapshot.

    Returns a sorted list of changed project-relative paths (new, modified or
    deleted), or None when the baseline is unusable (a finding is appended).
    """
    if not isinstance(baseline, dict) or baseline.get("schema") != BASELINE_SCHEMA:
        findings.append(Finding("TASK_BASELINE_INVALID", "baseline", "unsupported or missing baseline schema"))
        return None
    baseline_root = baseline.get("repository_root") or ""
    if os.path.normcase(os.path.realpath(baseline_root)) != os.path.normcase(os.path.realpath(root)):
        findings.append(Finding("TASK_BASELINE_INVALID", "baseline",
                                "baseline belongs to a different repository"))
        return None
    if work_unit_id and baseline.get("work_unit_id") != work_unit_id:
        findings.append(Finding("TASK_BASELINE_INVALID", "baseline",
                                "baseline work-unit id does not match"))
        return None
    baseline_files = baseline.get("files")
    if not isinstance(baseline_files, dict):
        findings.append(Finding("TASK_BASELINE_INVALID", "baseline",
                                "baseline files map is missing or malformed"))
        return None
    try:
        current_files = _enumerate_snapshot(root)
    except OSError as exc:
        findings.append(Finding("TASK_BASELINE_INVALID", "baseline",
                                "final-state collection failed: %s" % exc))
        return None
    changed = set()
    for path, digest in current_files.items():
        if path not in baseline_files:
            changed.add(path)
        elif baseline_files[path] != digest:
            changed.add(path)
    for path in baseline_files:
        if path not in current_files:
            changed.add(path)
    return sorted(changed)


def load_baseline(root, rel, findings):
    try:
        text = read_text(root, rel)
    except (FileNotFoundError, av.PathProblem, OSError, ValueError) as exc:
        findings.append(Finding("TASK_BASELINE_MISSING", rel, str(exc)))
        return None
    try:
        return json.loads(text)
    except ValueError as exc:
        findings.append(Finding("TASK_BASELINE_INVALID", rel, "malformed baseline JSON: %s" % exc))
        return None


def check_scope(changed_paths, allowed_value, findings):
    """Enforce Files/modules allowed with case-sensitive fnmatch patterns."""
    patterns = [part.strip().replace("\\", "/")
                for part in re.split(r"[,;\n]", allowed_value) if part.strip()]
    if not patterns:
        findings.append(Finding("TASK_FIELD_INVALID", "Files/modules allowed",
                                "cannot enforce scope without at least one path or pattern"))
        return
    if any(pattern.lower() == "all" for pattern in patterns):
        return
    for pattern in patterns:
        if (pattern.startswith("/") or re.match(r"^[A-Za-z]:", pattern)
                or ".." in pattern.split("/")):
            findings.append(Finding("TASK_FIELD_INVALID", "Files/modules allowed",
                                    "allowed pattern %r is absolute or contains '..'" % pattern))
    for path in changed_paths:
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            findings.append(Finding("TASK_SCOPE_VIOLATION", path,
                                    "changed path is not covered by Files/modules allowed"))


def check_snapshot(root_real, lock_rel, findings, verified):
    try:
        lock_full = av.resolve_inside(root_real, lock_rel)
    except av.PathProblem as exc:
        findings.append(Finding("SNAPSHOT_INVALID", lock_rel, str(exc)))
        return
    if os.path.lexists(lock_full):
        result = av.verify_project(root_real, lock_rel)
        for item in result.findings:
            findings.append(Finding("SNAPSHOT_" + item.code, item.subject, item.message))
        if not result.findings:
            verified.append("ASES snapshot, lock and approval record verify (exit 0).")
        return
    try:
        snapshot_full = av.resolve_inside(root_real, DEFAULT_SNAPSHOT_DIR)
    except av.PathProblem as exc:
        findings.append(Finding("SNAPSHOT_INVALID", DEFAULT_SNAPSHOT_DIR, str(exc)))
        return
    if os.path.lexists(snapshot_full):
        findings.append(Finding("SNAPSHOT_LOCK_MISSING", lock_rel,
                                "snapshot exists but no lock file does"))
        return
    try:
        constitution = av.resolve_inside(root_real, DEFAULT_CONSTITUTION)
    except av.PathProblem as exc:
        findings.append(Finding("CONSTITUTION_MISSING", DEFAULT_CONSTITUTION, str(exc)))
        return
    if not os.path.isfile(constitution):
        findings.append(Finding("CONSTITUTION_MISSING", DEFAULT_CONSTITUTION,
                                "no adopted snapshot and no root Constitution"))
    else:
        verified.append("Root CONSTITUTION.md is present (not an adopted UAM snapshot).")


def cmd_check(args):
    try:
        root = av.real_root(args.project_root)
    except ValueError as exc:
        print("ERROR (fail closed): %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    print("ASES GATE")
    print("Project root: %s" % root)
    print("Context: %s" % args.context)
    print("Task: %s" % args.task)
    if args.identity:
        print("Identity: %s" % args.identity)
    if args.changed_files:
        print("Changed files: %s" % args.changed_files)

    findings, verified = [], []
    check_snapshot(root, args.lock, findings, verified)

    identity = None
    try:
        context_text = read_text(root, args.context)
    except (FileNotFoundError, av.PathProblem, OSError, ValueError) as exc:
        findings.append(Finding("CONTEXT_MISSING" if isinstance(exc, FileNotFoundError) else "CONTEXT_INVALID",
                                args.context, str(exc)))
    else:
        identity = check_context(context_text, root, findings)

    task_values = None
    try:
        task_text = read_text(root, args.task)
    except (FileNotFoundError, av.PathProblem, OSError, ValueError) as exc:
        findings.append(Finding("TASK_MISSING" if isinstance(exc, FileNotFoundError) else "TASK_INVALID",
                                args.task, str(exc)))
    else:
        task_values = check_task(task_text, identity, findings)

    if args.identity:
        try:
            identity_path = av.resolve_inside(root, args.identity)
            identity_text = av.canonical_text_bytes(av.read_bytes(identity_path)).decode("utf-8")
            identity_record = json.loads(identity_text)
            identity_hash = ases_identity.compute_identity_hash(identity_record)
        except FileNotFoundError:
            findings.append(Finding("IDENTITY_INVALID", args.identity, "identity record not found"))
        except ases_identity.IdentityError as exc:
            findings.append(Finding("IDENTITY_INVALID", args.identity, str(exc)))
        except (av.PathProblem, OSError, ValueError) as exc:
            findings.append(Finding("IDENTITY_INVALID", args.identity,
                                    "cannot read identity record: %s" % exc))
        else:
            verified.append("Identity hash: %s" % identity_hash)

    if args.baseline:
        baseline = load_baseline(root, args.baseline, findings)
        if baseline is not None:
            changed_paths = compute_delta(root, baseline, args.work_unit, findings)
            if changed_paths is not None:
                baseline_self = args.baseline.replace("\\", "/")
                changed_paths = [p for p in changed_paths if p != baseline_self]
                if task_values is None:
                    findings.append(Finding("TASK_CHANGED_FILES_INVALID", args.baseline,
                                            "cannot check scope without a readable task record"))
                else:
                    check_scope(changed_paths, task_values.get("Files/modules allowed", ""), findings)
    elif args.changed_files:
        changed_paths = load_changed_files(root, args.changed_files, findings)
        if changed_paths is not None:
            if task_values is None:
                findings.append(Finding("TASK_CHANGED_FILES_INVALID", args.changed_files,
                                        "cannot check scope without a readable task record"))
            else:
                check_scope(changed_paths, task_values.get("Files/modules allowed", ""), findings)
    else:
        if args.legacy_collect:
            changed_paths = collect_git_changed_files(root, findings)
            if changed_paths is not None:
                if task_values is None:
                    findings.append(Finding("TASK_CHANGED_FILES_INVALID", "changed files",
                                            "cannot check scope without a readable task record"))
                else:
                    check_scope(changed_paths, task_values.get("Files/modules allowed", ""), findings)
            else:
                verified.append("Scope check skipped: not a git work tree and no --changed-files supplied.")
        elif _is_own_git_root(root):
            findings.append(Finding("TASK_CHANGED_FILES_MISSING", "changed files",
                                    "governed work unit has no baseline, changed-files list, or "
                                    "--legacy-collect; scope enforcement cannot be skipped"))
        else:
            verified.append("Scope check skipped: not a git work tree and no --changed-files supplied.")

    if verified:
        print("VERIFIED:")
        for line in verified:
            print("  - %s" % line)
    if findings:
        print("FINDINGS:")
        for item in findings:
            print("  [%s] %s: %s" % (item.code, item.subject, item.message))
        for code in sorted({item.code for item in findings}):
            base = code[len("SNAPSHOT_"):] if code.startswith("SNAPSHOT_") else code
            print("  fix %s: %s" % (code, HINTS.get(code, HINTS.get(base, ""))))
        print("RESULT: BLOCKED (%d finding(s)). Do not implement until these are resolved." % len(findings))
        return EXIT_BLOCKED

    print("RESULT: PASS. The project context and current task authorization are complete.")
    print("LIMITS: this is a document/consistency gate. It does not prove that an agent read or understood "
          "the documents, and it cannot prove that a Founder approval is genuine.")
    return EXIT_OK


INTENT_SCHEMA = "ases-intent-decision/1"

PROHIBITED_ACTIONS = (
    ("commit", re.compile(r"\bcommit\b", re.IGNORECASE), "commit is prohibited by the current task authorization"),
    ("push", re.compile(r"\bpush\b", re.IGNORECASE), "push is prohibited"),
    ("force-push", re.compile(r"force[-\s]?push", re.IGNORECASE), "force-push is prohibited"),
    ("pr-create", re.compile(r"\bpr-create\b", re.IGNORECASE), "pr-create is NOT AUTHORIZED"),
    ("credential", re.compile(r"\bcredential\b|\bpassphrase\b|\baccess\s+token\b|ghp_[A-Za-z0-9]|github_pat_", re.IGNORECASE),
     "credential/passphrase/access-token access is prohibited"),
    ("real-github", re.compile(r"real[-\s]?github|production\s+runtime|production\s+fault", re.IGNORECASE),
     "real-GitHub/production operations are prohibited"),
    ("unknown-retry", re.compile(r"retry\b[^\n]{0,40}\bUNKNOWN|UNKNOWN\s+operation", re.IGNORECASE),
     "UNKNOWN operation retry is prohibited"),
)

GOVERNANCE_CHANGES = (
    (re.compile(r"\bCONSTITUTION\b", re.IGNORECASE), "changing the Constitution requires Founder approval"),
    (re.compile(r"\bAPPROVED_DECISIONS\b", re.IGNORECASE), "changing Approved Decisions requires Founder approval"),
    (re.compile(r"\bCURRENT_TASK\b", re.IGNORECASE), "changing the task authorization requires Founder approval"),
    (re.compile(r"\bPROJECT_CONTEXT\b", re.IGNORECASE), "changing the project context requires Founder approval"),
)

OUT_OF_SCOPE_OBJECTIVES = (
    (re.compile(r"Universal[-\s]?Orchestrator", re.IGNORECASE), "Universal-Orchestrator is outside the approved Phase 1 scope"),
    (re.compile(r"\bHarness\b|\bHarness2\b", re.IGNORECASE), "Harness² is outside the approved Phase 1 scope"),
    (re.compile(r"\bUSHE\b", re.IGNORECASE), "USHE is outside the approved Phase 1 scope"),
)

PATH_TOKEN = re.compile(r"\b[\w./\\-]+(?:\.(?:py|ps1|md|json|yml|yaml|sh|js|ts|txt|diff|lock))\b")


def _task_fields(root, task_rel):
    try:
        text = read_text(root, task_rel)
    except (FileNotFoundError, av.PathProblem, OSError, ValueError):
        return {}
    return {name: field_values(text, name)[0] for name in ("Task ID", "Objective", "Files/modules allowed")
            if field_values(text, name)}


def load_approval(root, rel):
    """Load an explicit Founder approval record (ases-approval/1). Returns (operations, evidence)."""
    if not rel:
        return None, ""
    try:
        text = read_text(root, rel)
    except (FileNotFoundError, av.PathProblem, OSError, ValueError):
        return None, ""
    try:
        rec = json.loads(text)
    except ValueError:
        return None, ""
    if not isinstance(rec, dict) or rec.get("schema") != "ases-approval/1":
        return None, ""
    ops = rec.get("operations")
    if not isinstance(ops, list) or not all(isinstance(o, str) for o in ops):
        return None, ""
    evidence = rec.get("evidence", "")
    if not evidence:
        return None, ""
    return set(ops), evidence


def cmd_intent(args):
    try:
        root = av.real_root(args.project_root)
    except ValueError as exc:
        print("ERROR (fail closed): %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    instruction = (args.instruction or "").strip()
    if not instruction:
        print("ERROR (fail closed): empty instruction", file=sys.stderr)
        return EXIT_ERROR
    fields = _task_fields(root, args.task)
    allowed = fields.get("Files/modules allowed", "")

    approved_ops, approval_evidence = load_approval(root, getattr(args, "approval", None))

    decision = "ALLOW"
    reasons = []
    for op, pat, reason in PROHIBITED_ACTIONS:
        if pat.search(instruction):
            if approved_ops is not None and op in approved_ops:
                reasons.append("%s (explicit Founder approval: %s)" % (reason, approval_evidence))
            else:
                decision = "BLOCK"
                reasons.append(reason)
    for pat, reason in GOVERNANCE_CHANGES:
        if pat.search(instruction):
            if decision == "ALLOW":
                decision = "REQUIRE_FOUNDER_APPROVAL"
            reasons.append(reason)
    for pat, reason in OUT_OF_SCOPE_OBJECTIVES:
        if pat.search(instruction):
            if decision == "ALLOW":
                decision = "REQUIRE_FOUNDER_APPROVAL"
            reasons.append(reason)

    patterns = [p.strip().replace("\\", "/") for p in re.split(r"[,;\n]", allowed) if p.strip()]
    out_of_scope = []
    for token in sorted(set(PATH_TOKEN.findall(instruction))):
        path = token.strip().replace("\\", "/").strip("./")
        if not path or "/" not in path:
            continue  # bare filename is ambiguous; only full paths are deterministically checked
        if not patterns or not any(fnmatch.fnmatchcase(path, p) for p in patterns):
            out_of_scope.append(path)
    if out_of_scope:
        if decision == "ALLOW":
            decision = "BLOCK"
        reasons.append("out-of-scope path(s): %s" % ", ".join(out_of_scope))

    if (decision == "ALLOW" and not PATH_TOKEN.findall(instruction)
            and not any(pat.search(instruction) for _, pat, _ in PROHIBITED_ACTIONS)
            and not any(pat.search(instruction) for pat, _ in GOVERNANCE_CHANGES + OUT_OF_SCOPE_OBJECTIVES)):
        decision = "REVIEW_REQUIRED"
        reasons.append("instruction has no classifiable signal; review required")

    record = {
        "schema": INTENT_SCHEMA,
        "instruction_source": args.source,
        "work_unit_id": fields.get("Task ID", ""),
        "project_objective": fields.get("Objective", ""),
        "decision": decision,
        "reasons": reasons,
    }
    print(json.dumps(record, indent=2, sort_keys=True))
    if decision == "ALLOW":
        return EXIT_OK
    if decision == "BLOCK":
        return EXIT_BLOCKED
    return 2


def cmd_baseline(args):
    try:
        root = av.real_root(args.project_root)
    except ValueError as exc:
        print("ERROR (fail closed): %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    try:
        snapshot = capture_baseline(root, args.work_unit)
    except OSError as exc:
        print("ERROR (fail closed): baseline capture failed: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    text = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if args.output:
        try:
            out = av.resolve_inside(root, args.output)
        except av.PathProblem as exc:
            print("ERROR (fail closed): %s" % exc, file=sys.stderr)
            return EXIT_ERROR
        with open(out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("Baseline written to %s (%d files)." % (args.output, len(snapshot["files"])))
    else:
        sys.stdout.write(text)
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(prog="ases_gate.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check project context, current task and ASES snapshot")
    check.add_argument("--project-root", default=".")
    check.add_argument("--context", default=DEFAULT_CONTEXT)
    check.add_argument("--task", default=DEFAULT_TASK)
    check.add_argument("--lock", default=DEFAULT_LOCK)
    check.add_argument("--changed-files",
                       help="optional newline-separated changed-file list for scope enforcement")
    check.add_argument("--baseline",
                       help="optional project-relative baseline snapshot for per-work-unit delta")
    check.add_argument("--work-unit",
                       help="expected work-unit id validated against a supplied baseline")
    check.add_argument("--legacy-collect", action="store_true",
                       help="explicitly use the legacy full-tree git collector (non-baseline diagnostic)")
    check.add_argument("--identity",
                       help="optional project-relative JSON task-identity record to validate and hash")
    check.set_defaults(func=cmd_check)
    base = sub.add_parser("baseline", help="capture a per-work-unit baseline snapshot")
    base.add_argument("--project-root", default=".")
    base.add_argument("--work-unit", required=True, help="work-unit identifier")
    base.add_argument("--output", help="optional output path (default: stdout)")
    base.set_defaults(func=cmd_baseline)
    intent = sub.add_parser("intent", help="deterministic intent-integrity & scope decision (IISE)")
    intent.add_argument("--project-root", default=".")
    intent.add_argument("--task", default=DEFAULT_TASK)
    intent.add_argument("--instruction", help="the incoming instruction text to evaluate")
    intent.add_argument("--source", default="unknown", help="instruction source label (founder/agent/tool-output/repository-doc)")
    intent.add_argument("--approval", help="optional project-relative Founder approval record (ases-approval/1)")
    intent.set_defaults(func=cmd_intent)
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
    except Exception as exc:  # fail closed
        print("ERROR (fail closed): %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
