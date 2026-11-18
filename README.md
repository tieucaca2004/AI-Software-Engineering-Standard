# AI Software Engineering Standard (ASES)

- **Repository:** `AI-Software-Engineering-Standard`
- **Standard:** ASES Constitution 1.0
- **Language:** Vietnamese
**Purpose:** A single, version-controlled source of engineering governance for AI-assisted software projects.

## Core rule

Every AI coding session must load and follow the project's ASES instructions and the complete `CONSTITUTION.md` before performing work. A milestone is not officially integrated until the Founder explicitly accepts it.

## Repository contents

- `CONSTITUTION.md` — canonical, complete constitution.
- `enforcement/` — instructions for supported AI coding tools.
- `templates/` — project adoption, milestone, change request and compliance templates.
- `scripts/` — local preflight and repository policy checks.
- `.github/workflows/` — CI validation of the policy files.
- `docs/` — adoption, enforcement limits and operating procedure.

## Quick start

1. Read `CONSTITUTION.md`.
2. Review `docs/ENFORCEMENT_MODEL.md` and `docs/PROJECT_ADOPTION.md`.
3. Copy the appropriate instruction files into each project using the project adoption procedure.
4. Run the preflight script before assigning implementation work.
5. Require a Milestone Completion Report and explicit Founder acceptance before official integration.

## Important limitation

Instruction files, prompts and preflight scripts improve compliance but cannot mathematically prove that a model internally read or obeyed a document. Stronger controls require repository permissions, protected branches, required CI checks, human review and restricted production credentials.

## Versioning

The Constitution is the canonical policy. Project-level instruction files are enforcement adapters and must not weaken or contradict it. Amendments require an approved change and a versioned release.
