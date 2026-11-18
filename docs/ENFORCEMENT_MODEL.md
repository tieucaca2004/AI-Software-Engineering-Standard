# ASES Enforcement Model

## 1. Objective

Make the Constitution reliably available to AI coding tools and make policy violations visible and difficult to merge. No instruction file can guarantee a model's internal reasoning or prove that it complied.

## 2. Enforcement layers

### Layer A — Tool instructions
- Claude Code: root `CLAUDE.md`, importing `CONSTITUTION.md`.
- Codex and compatible agents: root `AGENTS.md`.
- Cursor: install `enforcement/cursor/ases.mdc` as `.cursor/rules/ases.mdc`.
- GitHub Copilot: install `enforcement/copilot-instructions.md` as `.github/copilot-instructions.md`.
- Other agents: adapt `enforcement/generic/PROJECT_AI_INSTRUCTIONS.md`.

Tool support and instruction discovery can change. Verify the current tool's documented instruction-loading behavior when adopting or upgrading it.

### Layer B — Preflight
Run `python scripts/ases_preflight.py --project-root .` at the start of a work session. It checks that required policy files exist and prints the required reading sequence. It does not prove that a model read or understood the content.

In an adopted project, run `python docs/governance/ases/scripts/ases_verify.py verify --project-root .` instead. It verifies the pinned snapshot offline with SHA-256 (see `docs/UAM.md`). It proves integrity of the vendored files only; it does not prove approval or agent compliance.

### Layer C — CI
The GitHub Actions workflow checks that the Constitution and core instruction files remain present and that the policy version is recorded. Configure the workflow as a required status check in branch protection/rulesets.

### Layer D — Human approval
Require review and explicit Founder acceptance before official integration. Protect the production branch and restrict write/admin permissions.

### Layer E — Runtime permissions
Use least-privilege credentials. Keep production secrets and destructive capabilities unavailable to ordinary coding agents where feasible. Require human approval for migrations, destructive operations and production deployment.

## 3. Session protocol

At the beginning of every new AI work session:
1. Load repository instructions.
2. Read the complete Constitution.
3. Read project Approved Decisions and current scope.
4. Inspect Git status and current milestone.
5. State task scope and acceptance criteria.
6. Stop if documents conflict or are missing.

At the end:
1. Report implementation and changed files.
2. Report exact tests executed and results.
3. Attach evidence.
4. Report deviations, known issues and risks.
5. Report Git status.
6. Wait for Founder acceptance.

## 4. Important limitations

- Prompt/instruction files are guidance, not a security sandbox.
- A preflight script checks file presence, not model cognition.
- CI can prevent merging when checks fail, but cannot establish that runtime behavior is correct.
- Branch protection and required reviews must be configured in GitHub settings.
- High-assurance enforcement requires restricted permissions, protected environments, required human reviews and external testing.
