#!/usr/bin/env python3
"""CI policy-file integrity check."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "CONSTITUTION.md",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "VERSION",
    "enforcement/cursor/ases.mdc",
    "enforcement/copilot-instructions.md",
    "templates/APPROVED_DECISIONS.md",
    "templates/MILESTONE_COMPLETION_REPORT.md",
    "templates/CHANGE_REQUEST.md",
    "docs/ENFORCEMENT_MODEL.md",
    "docs/PROJECT_ADOPTION.md",
    "docs/UAM.md",
    "ases-manifest.json",
    "scripts/ases_verify.py",
    "templates/ASES_APPROVAL_RECORD.md",
    "tests/test_ases_verify.py",
]

missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
if missing:
    print("ASES POLICY CHECK FAILED")
    for item in missing:
        print(f"MISSING: {item}")
    sys.exit(1)

constitution = (ROOT / "CONSTITUTION.md").read_text(encoding="utf-8")
if len(constitution.strip()) < 5000:
    print("ASES POLICY CHECK FAILED: Constitution appears unexpectedly short.")
    sys.exit(1)

print("ASES POLICY CHECK PASSED: required files exist and Constitution is non-empty.")
