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
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
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
    "TASK_CHANGED_FILES_MISSING": "Create the changed-files list or run without --changed-files before implementation.",
    "TASK_CHANGED_FILES_INVALID": "Changed-file paths must be project-relative, with no '..' or drive prefix.",
    "TASK_SCOPE_VIOLATION": "The changed path is outside Files/modules allowed. Stop or obtain a new task authorization.",
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
BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$")


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

    if args.changed_files:
        changed_paths = load_changed_files(root, args.changed_files, findings)
        if changed_paths is not None:
            if task_values is None:
                findings.append(Finding("TASK_CHANGED_FILES_INVALID", args.changed_files,
                                        "cannot check scope without a readable task record"))
            else:
                check_scope(changed_paths, task_values.get("Files/modules allowed", ""), findings)

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
    check.set_defaults(func=cmd_check)
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
