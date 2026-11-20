# ASES Enforcement Model

## 1. Objective

Make the Constitution, the Project Context and the current task authorization reliably available
to AI coding tools and make policy violations visible and difficult to merge. No instruction file
can guarantee a model's internal reasoning or prove that it complied.

## 2. Enforcement layers

### Layer A — Tool instructions and task records
- Claude Code: root `CLAUDE.md`, importing `CONSTITUTION.md`.
- Codex and compatible agents: root `AGENTS.md`.
- Cursor: install `enforcement/cursor/ases.mdc` as `.cursor/rules/ases.mdc`.
- GitHub Copilot: install `enforcement/copilot-instructions.md` as `.github/copilot-instructions.md`.
- Other agents: adapt `enforcement/generic/PROJECT_AI_INSTRUCTIONS.md`.
- Every adopted project also has `docs/governance/PROJECT_CONTEXT.md` and
  `docs/governance/CURRENT_TASK.md`, which the tool instructions require the agent to read.

Tool support and instruction discovery can change. Verify the current tool's documented
instruction-loading behavior when adopting or upgrading it.

### Layer B — Preflight and gate
- ASES source repository: `python scripts/ases_preflight.py --project-root .` checks the standard's
  own policy files and prints the reading sequence. It does not prove that a model read them.
- Adopted project: `python docs/governance/ases/scripts/ases_gate.py check --project-root . --task
  docs/governance/CURRENT_TASK.md`. It verifies the pinned snapshot, checks the Project Context's
  required sections/fields/requirements and the approved-decisions file it references, and requires
  an `Authorized` task record. When CI supplies `--changed-files`, it also blocks changes outside the
  task's allowed paths. It is read-only and offline.
- The gate is deterministic and fail-closed, but it evaluates documents. It cannot prove reading,
  understanding or the authenticity of a self-declared approval.

### Layer C — CI
The ASES workflow checks policy-file presence, the Constitution hash, the snapshot manifest, and
all governance tests. Adopted projects should install `templates/ases-governance.yml`, which runs
`ases_verify.py verify` and `ases_gate.py check` as required status checks. Configure the relevant
job as a required status check in branch protection/rulesets.

### Layer D — Human approval
Require review and explicit Founder acceptance before official integration. Protect the production
branch and restrict write/admin permissions. Require Code Owner review for `docs/governance/**`
and all policy files.

### Layer E — Runtime permissions
Use least-privilege credentials. Keep production secrets and destructive capabilities unavailable
to ordinary coding agents where feasible. Require human approval for migrations, destructive
operations and production deployment.

## 3. Session protocol

At the beginning of every new AI work session:
1. Load repository instructions.
2. Read the complete Constitution.
3. Read the Project Context, Approved Decisions and current scope/milestone.
4. Read the `Authorized` current-task record and run the gate in an adopted project.
5. Inspect Git status and current milestone.
6. State task scope and acceptance criteria.
7. Stop if documents conflict, are missing, are incomplete or the gate blocks.

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
- The gate checks document completeness, not truth or reading.
- An approval record is self-declared; only protected review and explicit human decisions provide
  real approval assurance.
- CI can prevent merging when checks fail, but cannot establish that runtime behavior is correct.
- Branch protection and required reviews must be configured in GitHub settings.
- High-assurance enforcement requires restricted permissions, protected environments, required
  human reviews and external testing.
