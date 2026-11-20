#!/usr/bin/env python3
"""CI policy-file integrity check."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ases_verify  # noqa: E402

# Canonical (text-lf-v1) SHA-256 of the Founder-approved ASES Constitution 1.0.
# A mismatch means the Constitution changed. Do not update this constant without
# an explicit Founder-approved constitutional amendment and a versioned release.
CONSTITUTION_SHA256 = "bf3fef6fc8f6323d30d76f90b94c64851f3d03a99a7de9a097772191dc1d0982"

REQUIRED = [
    "CONSTITUTION.md",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "VERSION",
    "CHANGELOG.md",
    "ases-manifest.json",
    "docs/ENFORCEMENT_MODEL.md",
    "docs/LIFECYCLE_GATES.md",
    "docs/PROJECT_ADOPTION.md",
    "docs/RELEASE_AND_CHANGE_CONTROL.md",
    "docs/UAM.md",
    "enforcement/copilot-instructions.md",
    "enforcement/cursor/ases.mdc",
    "enforcement/generic/PROJECT_AI_INSTRUCTIONS.md",
    "scripts/ases_gate.py",
    "scripts/ases_verify.py",
    "templates/APPROVED_DECISIONS.md",
    "templates/ASES_APPROVAL_RECORD.md",
    "templates/CHANGE_REQUEST.md",
    "templates/CURRENT_TASK.md",
    "templates/MILESTONE_COMPLETION_REPORT.md",
    "templates/PROJECT_COMPLIANCE_PROFILE.md",
    "templates/PROJECT_CONTEXT.md",
    "templates/ases-governance.yml",
    "tests/test_ases_verify.py",
    "tests/test_ases_gate.py",
    "tests/test_adapters.py",
    "tests/test_policy.py",
]


def fail(message):
    print("ASES POLICY CHECK FAILED: %s" % message)
    return 1


def main():
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        print("ASES POLICY CHECK FAILED")
        for item in missing:
            print("MISSING: %s" % item)
        return 1

    constitution = (ROOT / "CONSTITUTION.md").read_bytes()
    try:
        digest = ases_verify.file_hash(ROOT / "CONSTITUTION.md")
    except ValueError as exc:
        return fail("Constitution is not canonical text: %s" % exc)
    if len(constitution.strip()) < 5000:
        return fail("Constitution appears unexpectedly short")
    if digest != CONSTITUTION_SHA256:
        return fail("Constitution SHA-256 %s does not match the approved Constitution 1.0 hash" % digest)

    try:
        manifest = json.loads((ROOT / "ases-manifest.json").read_text(encoding="utf-8"))
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return fail("cannot read manifest/version: %s" % exc)
    if not isinstance(manifest, dict):
        return fail("ases-manifest.json root must be an object")
    if manifest.get("schema") != "ases-manifest/1":
        return fail("ases-manifest.json schema is not ases-manifest/1")
    files = manifest.get("files")
    if not isinstance(files, list):
        return fail("ases-manifest.json files must be a non-empty list")
    if manifest.get("ases_version") != version:
        return fail("VERSION (%s) does not match manifest ases_version (%s)" % (
            version, manifest.get("ases_version")))
    listed = {entry.get("path") for entry in files if isinstance(entry, dict)}
    managed = set(ases_verify.MANAGED_FILES)
    if listed != managed:
        return fail("manifest file set does not match the managed set")

    print("ASES POLICY CHECK PASSED: required files exist, Constitution 1.0 is intact, "
          "and VERSION matches the manifest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
