# ASES Independent Review Package

**Status:** Prepared for independent human review. This document is not a review, approval, acceptance or merge authorization.

**Baseline:** reviewed implementation `03c3b7f` (pre-audit) plus the defect-fix commit included in this
PR; `main` at `14b9a82`; PR #1 and PR #2 open.

This package reviews the implementation in PR #1. This file is a review aid and may be amended
later; any such amendment does not change the reviewed implementation commits.

## 1. Purpose

Give an independent reviewer the scope, evidence, known limits and focus areas needed to review
PR #1 and PR #2 without relying on the author's summary.

## 2. PR #1 — UAM MVP and governance enforcement

### 2.1 Scope

- Branch: `uam-mvp`
- Pre-audit implementation head: `03c3b7f`
- Base: `main` at `14b9a82`
- Implementation commits: 9 (8 pre-audit commits + 1 defect-fix commit)
- The review-package file and any later documentation amendment are not implementation commits.
- No merge, approval or Founder acceptance is claimed.

### 2.2 Change map

| Area | Files |
|---|---|
| Constitution | `CONSTITUTION.md` — unchanged |
| Lifecycle | `docs/LIFECYCLE_GATES.md` |
| Project governance | `templates/PROJECT_CONTEXT.md`, `templates/CURRENT_TASK.md`, `templates/APPROVED_DECISIONS.md`, `templates/PROJECT_COMPLIANCE_PROFILE.md`, `templates/MILESTONE_COMPLETION_REPORT.md` |
| Task-entry gate | `scripts/ases_gate.py`, `tests/test_ases_gate.py` |
| UAM snapshot/lock/verify | `ases-manifest.json`, `scripts/ases_verify.py`, `tests/test_ases_verify.py`, `docs/UAM.md` |
| Founder approval | `templates/ASES_APPROVAL_RECORD.md` |
| AI adapters | `AGENTS.md`, `CLAUDE.md`, `enforcement/copilot-instructions.md`, `enforcement/cursor/ases.mdc`, `enforcement/generic/PROJECT_AI_INSTRUCTIONS.md` |
| CI | `.github/workflows/ases-policy.yml`, `templates/ases-governance.yml` |
| Adoption | `docs/PROJECT_ADOPTION.md`, `README.md`, `CHANGELOG.md`, `VERSION` |

### 2.3 Enforcement behavior to review

1. `ases_gate.py` verifies the adopted snapshot/lock/approval when a lock exists.
2. It validates the Project Context sections, requirements, acceptance criteria and current milestone.
3. It requires the approved-decisions file referenced by the context to exist and be non-empty.
4. It requires `CURRENT_TASK.md` with `Status: Authorized` and explicit fields.
5. It rejects self-authorization, placeholders, project mismatch and invalid dates.
6. With `--changed-files`, it rejects paths outside `Files/modules allowed`.
7. It is read-only and offline; exit codes are 0 pass, 1 blocked, 2 usage/error.

### 2.4 Test evidence

Command:

```text
python -m unittest discover -s tests -q
```

Result after the defect-fix commit (suite grew from 101 to 102 tests):

```text
Ran 102 tests in 37.489s
OK (skipped=1)
```

Key coverage:

| Requirement | Test group |
|---|---|
| Missing/invalid context rejected | `ContextChecks` |
| Missing/non-authorized task rejected | `TaskChecks` |
| Self-authorization rejected | `test_task_self_authorization_rejected` |
| Out-of-scope changes rejected | `ScopeChecks` |
| Adopted CI valid/invalid behavior | `AdoptedProjectCI` |
| Snapshot tampering detected | `FileIntegrity`, `SnapshotChecks` |
| Version lock mismatch detected | `Versions` |
| Approval record cannot be self-declared | `ApprovalRecord` |
| Adapters require governance | `test_adapters.py` |
| Repository policy/Constitution intact | `test_policy.py` |
| Malformed manifest handled cleanly | `test_policy.py` |

The single skip is `test_symlink_in_snapshot_rejected` because Windows did not permit symlink
creation in the local environment. Windows junction rejection is tested and passes.

### 2.5 CI evidence

- [Run 44745255295](https://github.com/tieucaca2004/AI-Software-Engineering-Standard/actions/runs/44745255295) — success at `03c3b7f`.
- [Run 44748233466](https://github.com/tieucaca2004/AI-Software-Engineering-Standard/actions/runs/44748233466) — success at the prior review-package commit `adce730`.
- Required check: `ASES policy files`.
- Workflow steps: policy check, preflight, manifest check, full tests.

### 2.6 Security evidence

- `main-protection` ruleset active for `refs/heads/main`.
- Required approving reviews: 1.
- Dismiss stale reviews: yes.
- Require Code Owner review: yes.
- Required review thread resolution: yes.
- Strict required status checks: yes.
- Required context: `ASES policy files`.
- Bypass actors: `null` (none).
- No secrets or credentials found in the diff.
- No force-push, ruleset change or merge performed.

### 2.7 Known limitations reviewer must check

- F1/F2 identity hashing is **not implemented**: the exact nine-field contract and
  `schema_version = 3` record shape were not found in accessible sources.
- The approval record is self-declared; it cannot prove a genuine Founder decision.
- Adopted-project CI is tested as a local CI-equivalent against a real temporary Git repository,
  not as a GitHub-hosted workflow in a separate repository.
- The gate cannot prove that an AI agent read or understood the documents.
- CODEOWNERS is not on `main`; Code Owner review is configured but not effective until PR #2 merges.
- No independent review or Founder acceptance exists.

### 2.8 Reviewer focus checklist

1. Can any gate path produce PASS with missing/incomplete context, a non-authorized task,
   self-authorization or an out-of-scope changed file?
2. Does `--changed-files` parsing handle traversal, absolute paths, symlinks/junctions and
   unexpected file lists safely?
3. Does the approved-decisions file check resolve only project-relative paths and fail closed?
4. Does `ases_verify.py` verify all lock/manifest/version/approval relationships without a bypass?
5. Do all five adapters state the same mandatory behavior and failure response?
6. Does the adopted CI template actually fail a repository missing governance files, and does its
   diff step work on a real PR?
7. Are the docs honest about self-declared approval, reading limitations and the F1/F2 gap?
8. Does the candidate remain within the approved five-component UAM scope?

## 3. PR #2 — CODEOWNERS

- Branch: `security/codeowners`
- Head: `37cbdc6`
- File: `.github/CODEOWNERS`
- Content:

```text
*  @tieucaca2004
```

- Syntax and location are valid for GitHub Code Owners.
- `main` currently has no `.github/CODEOWNERS` (`404`).
- The ruleset already requires Code Owner review, so PR #2 becomes effective only after merge.
- This package does not authorize that merge.

## 4. F1/F2 contract status

**Founder-approved (2026-11-18):**

- F1: `risk_level` is excluded from the Identity Hash; the hash uses exactly 9 identity fields.
- F2: `schema_version = 3` is kept; no identity algorithm version is added.

**AI-recovered technical details (UNVERIFIED — NOT CONFIRMED AS FOUNDER-APPROVED):**

A proposed nine-field list and proposed canonicalization rules are retained for reference in
`docs/IDENTITY_CONTRACT.md`. They are **not** verified as Founder-approved and must not be treated
as an implementation-ready contract.

**Unresolved (block implementation):**

- hash algorithm;
- final canonical payload structure;
- whether `schema_version = 3` participates in the hash payload;
- byte serialization (encoding, separators, escaping);
- nested-value and data-type handling.

Identity Hash implementation remains **BLOCKED** until the technical contract is complete and
confirmed. No identity hashing is implemented. No substitute contract was invented.

## 5. Review outcome handling

- Independent reviewer must record findings separately.
- The author does not approve or merge.
- Founder acceptance remains separate from any review.
- A passing CI run is not acceptance.
