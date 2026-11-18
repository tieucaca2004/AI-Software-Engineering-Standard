#!/usr/bin/env python3
"""ASES local preflight: checks policy file presence; does not prove model cognition."""
from pathlib import Path
import argparse
import sys

REQUIRED = [
    "CONSTITUTION.md",
    "AGENTS.md",
    "README.md",
    "VERSION",
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".", help="Repository root")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    print("ASES PREFLIGHT")
    print(f"Project root: {root}")
    missing = [name for name in REQUIRED if not (root / name).is_file()]

    if missing:
        print("BLOCKED: required ASES files are missing:")
        for item in missing:
            print(f" - {item}")
        return 2

    print("Policy files present.")
    print("MANDATORY READING SEQUENCE:")
    print("  1. CONSTITUTION.md (read completely)")
    print("  2. Project APPROVED_DECISIONS.md")
    print("  3. Project scope, constraints and current milestone")
    print("  4. Inspect Git status and authorized task scope")
    print("")
    print("LIMITATION: this script verifies file presence only.")
    print("It cannot prove that an AI model read, understood or obeyed these files.")
    print("Proceed only after the agent has actually loaded and reviewed the documents.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
