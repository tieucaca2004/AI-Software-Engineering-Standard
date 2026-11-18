# Changelog

## Unreleased
- Added the Universal Adoption Mechanism (UAM) MVP: vendored snapshot manifest (`ases-manifest.json`), project version lock, offline read-only SHA-256 verifier (`scripts/ases_verify.py`), version-transition approval record template, and `docs/UAM.md`.
- Rewrote `docs/PROJECT_ADOPTION.md` around the pinned-snapshot layout (`docs/governance/ases/`); existing project-owned instruction files are never overwritten.
- Cursor and Copilot adapters now name the snapshot path of the Constitution. Constitution content is unchanged.
- `VERSION` is intentionally not changed here; bumping it is a separate release decision.

## 1.0.0 — 2026-11-18
- Initial ASES constitution repository.
- Added AI-tool instruction adapters.
- Added project adoption templates.
- Added local preflight and CI policy checks.
- Added explicit limitations and human acceptance controls.
