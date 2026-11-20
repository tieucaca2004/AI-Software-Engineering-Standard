#!/usr/bin/env python3
"""ASES local preflight for the ASES source repository.

It checks that the standard's own policy files are present and prints the
mandatory reading sequence. It does not prove model cognition. Adopted projects
must use docs/governance/ases/scripts/ases_gate.py instead.
"""
from pathlib import Path
import argparse
import sys

REQUIRED = [
    "CONSTITUTION.md",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "VERSION",
    "CHANGELOG.md",
    "ases-manifest.json",
    "docs/LIFECYCLE_GATES.md",
    "docs/PROJECT_ADOPTION.md",
    "docs/UAM.md",
    "scripts/ases_gate.py",
    "scripts/ases_verify.py",
    "templates/PROJECT_CONTEXT.md",
    "templates/CURRENT_TASK.md",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".", help="Repository root")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    print("ASES PREFLIGHT")
    print("Project root: %s" % root)

    adopted = (root / "docs" / "governance" / "ases.lock.json").exists() or (
        root / "docs" / "governance" / "ases").is_dir()
    if adopted:
        print("ADOPTED PROJECT DETECTED: use the project gate instead:")
        print("  python docs/governance/ases/scripts/ases_gate.py check "
              "--project-root . --task docs/governance/CURRENT_TASK.md")
        print("This preflight checks the ASES source repository, not an adopted project.")
        return 0

    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        print("BLOCKED: required ASES files are missing:")
        for item in missing:
            print(" - %s" % item)
        print("Do not implement around a missing policy file.")
        return 2

    print("Policy files present.")
    print("MANDATORY READING SEQUENCE:")
    print("  1. CONSTITUTION.md (read completely)")
    print("  2. docs/LIFECYCLE_GATES.md (G0-G7)")
    print("  3. Project PROJECT_CONTEXT.md and APPROVED_DECISIONS.md")
    print("  4. Project scope, constraints, current milestone and CURRENT_TASK.md")
    print("  5. Inspect Git status and authorized task scope")
    print("")
    print("ADOPTED PROJECTS: run ases_gate.py before implementation; this preflight")
    print("does not check the Project Context, task authorization or snapshot integrity.")
    print("")
    print("LIMITATION: this script verifies file presence only.")
    print("It cannot prove that an AI model read, understood or obeyed these files.")
    print("Proceed only after the agent has actually loaded and reviewed the documents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
