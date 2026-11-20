# Changelog

## 1.1.0 — 2026-11-20 (candidate; Founder acceptance pending)

- Added the Universal Adoption Mechanism (UAM) MVP: vendored snapshot manifest
  (`ases-manifest.json`), project version lock, offline read-only SHA-256 verifier
  (`scripts/ases_verify.py`), version-transition approval record template, and `docs/UAM.md`.
- Added the mandatory Project Context / Specification format (`templates/PROJECT_CONTEXT.md`)
  and the task-entry authorization record (`templates/CURRENT_TASK.md`).
- Added `scripts/ases_gate.py`, an offline read-only gate that blocks implementation when the
  Project Context is missing or incomplete, the current task is not explicitly authorized, or
  the adopted ASES snapshot/lock/approval record does not verify. With `--changed-files`, it also
  blocks changes outside the task's `Files/modules allowed` patterns. It also checks that the
  approved-decisions file referenced by the Project Context exists and is non-empty.
- Added `docs/LIFECYCLE_GATES.md` as the operational G0–G7 gate and evidence reference.
- Updated AI adapters (Codex/AGENTS, Claude Code, Cursor, Copilot, generic) to require the
  Project Context, the current task record and the gate.
- Expanded the ASES-managed snapshot to include the adoption, lifecycle, approval, context,
  task, milestone and compliance templates that adopted projects need.
- UAM hardening: `lock` now refuses to print a lock unless the snapshot itself verifies, and
  unexpected empty directories inside the snapshot are detected.
- Added CI governance tests and an adopted-project workflow template
  (`templates/ases-governance.yml`).
- The Constitution is unchanged at ASES Constitution 1.0. This release adds enforcement
  tooling and documentation; it does not amend the Constitution.

## 1.0.0 — 2026-11-18

- Initial ASES constitution repository.
- Added AI-tool instruction adapters.
- Added project adoption templates.
- Added local preflight and CI policy checks.
- Added explicit limitations and human acceptance controls.
