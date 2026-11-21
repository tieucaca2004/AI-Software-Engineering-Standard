# AI Software Engineering Standard (ASES)

- **Repository:** `AI-Software-Engineering-Standard`
- **Standard release:** ASES 1.1.0 (candidate)
- **Constitution:** ASES Constitution 1.0 (unchanged)
- **Language:** Vietnamese (Constitution); English (operational docs)
- **Purpose:** A single, version-controlled source of engineering governance for AI-assisted software projects.

## Core rule

Every AI coding session must load and follow the project's authoritative Constitution in full:
`CONSTITUTION.md` in the ASES source repository, or `<snapshot_dir>/CONSTITUTION.md` in an adopted
project. In an adopted project, it must also load the project's `PROJECT_CONTEXT.md`, approved
decisions and an `Authorized` current-task record. A milestone is not officially integrated until
the Founder explicitly accepts it.

## Repository contents

- `CONSTITUTION.md` — canonical, complete Constitution (version 1.0, unchanged).
- `docs/LIFECYCLE_GATES.md` — operational G0–G7 gate and evidence requirements.
- `docs/PROJECT_ADOPTION.md` — the authoritative adoption and upgrade procedure.
- `docs/UAM.md` — the Universal Adoption Mechanism (UAM) MVP reference.
- `enforcement/` — instructions for supported AI coding tools.
- `templates/` — project context, current task, task identity, approval, milestone, change and compliance records.
- `scripts/ases_verify.py` — offline, read-only snapshot/lock/approval verifier.
- `scripts/ases_gate.py` — offline project-context and task-entry governance gate.
- `scripts/ases_identity.py` — task Identity Hash (validation, canonicalization, SHA-256).
- `ases-manifest.json` — SHA-256 manifest of the ASES-managed snapshot.
- `tests/` — unit, CLI, adapter and policy tests.
- `.github/workflows/` — CI validation of policy, manifest and tests.

## Quick start

1. Read `CONSTITUTION.md` in full.
2. Review `docs/ENFORCEMENT_MODEL.md`, `docs/LIFECYCLE_GATES.md` and `docs/PROJECT_ADOPTION.md`.
3. Adopt the pinned snapshot into the project and connect its AI tools.
4. Create `docs/governance/PROJECT_CONTEXT.md` from the template before implementation.
5. Create `docs/governance/CURRENT_TASK.md` from the template for each task; it must say `Status: Authorized`.
6. Run the gate before work:
   `python docs/governance/ases/scripts/ases_gate.py check --project-root . --task docs/governance/CURRENT_TASK.md`
   In CI, add `--changed-files changed-files.txt` so changes outside the task's allowed paths block.
7. Enable the CI workflow from `templates/ases-governance.yml`.
8. Require a Milestone Completion Report and explicit Founder acceptance before official integration.

## UAM MVP boundary

The approved UAM MVP has exactly five components: Constitution Snapshot, AI Adapters, Version
Lock, Integrity Verify and Founder Approval. The project context and task-entry gate are ASES
core governance controls, not additional UAM components. There is no installer, updater,
dashboard, telemetry, fleet management or signature/key infrastructure.

## Important limitation

Instruction files, prompts, preflight scripts and gates improve compliance, but they cannot
mathematically prove that a model internally read or obeyed a document. They also cannot prove
that a self-declared Founder approval record is genuine. Stronger controls require repository
permissions, protected branches, required CI checks, human review and restricted credentials.

## Versioning

The Constitution is the canonical policy. Project-level instruction files are enforcement
adapters and must not weaken or contradict it. Amendments to the Constitution require an
approved Change Request and a versioned release. The 1.1.0 candidate adds enforcement tooling
without changing the Constitution.
