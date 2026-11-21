# ASES Independent Review Package

**Status:** Prepared for independent human review. This document is not a review, approval, acceptance or merge authorization.

**Implementation review baseline:**
- PR #1 implementation snapshot: `5a57e2e` (25 commits, 35 changed files, +4,760 / −123).
- Subsequent commits that only synchronize this review package do not change the reviewed implementation baseline.
- PR #1 base: `main` at `6cffc35` (after PR #2 CODEOWNERS merge).
- PR #2: **MERGED** — `.github/CODEOWNERS` is now on `main`.
- Implementation baseline: identity hash implemented at `f47d6ee`; JCS fix `7a569fb`;
  schema_version type fix `6ff8b00`. Later commits are documentation/reconciliation only.

This package reviews the implementation in PR #1. This file is a review aid and may be amended
later; any such amendment does not change the reviewed implementation commits.

## 1. Purpose

Give an independent reviewer the scope, evidence, known limits and focus areas needed to review
PR #1 without relying on the author's summary.

## 2. PR #1 — UAM MVP, governance enforcement and Identity Hash

### 2.1 Scope

- Branch: `uam-mvp`.
- Base: `main` at `6cffc35`.
- Implementation baseline: 25 commits from `1bf57ce` through `5a57e2e` (35 changed files, +4,760 / −123).
- No merge, approval or Founder acceptance is claimed for PR #1 itself.

### 2.2 Change map

| Area | Files |
|---|---|
| Constitution | `CONSTITUTION.md` — unchanged (SHA-256 `bf3fef6f…0982`) |
| Lifecycle | `docs/LIFECYCLE_GATES.md` |
| Project governance | `templates/PROJECT_CONTEXT.md`, `templates/CURRENT_TASK.md`, `templates/APPROVED_DECISIONS.md`, `templates/PROJECT_COMPLIANCE_PROFILE.md`, `templates/MILESTONE_COMPLETION_REPORT.md` |
| Task-entry gate | `scripts/ases_gate.py`, `tests/test_ases_gate.py` |
| Identity Hash | `scripts/ases_identity.py`, `templates/TASK_IDENTITY.json`, `tests/test_ases_identity.py`, `docs/IDENTITY_CONTRACT.md`, `docs/FOUNDER_IDENTITY_DECISIONS.md` |
| UAM snapshot/lock/verify | `ases-manifest.json`, `scripts/ases_verify.py`, `tests/test_ases_verify.py`, `docs/UAM.md` |
| Founder approval | `templates/ASES_APPROVAL_RECORD.md` |
| AI adapters | `AGENTS.md`, `CLAUDE.md`, `enforcement/copilot-instructions.md`, `enforcement/cursor/ases.mdc`, `enforcement/generic/PROJECT_AI_INSTRUCTIONS.md` |
| CI | `.github/workflows/ases-policy.yml`, `templates/ases-governance.yml` |
| Adoption/release | `docs/PROJECT_ADOPTION.md`, `README.md`, `CHANGELOG.md`, `VERSION` |
| Review aid | `docs/REVIEW_PACKAGE.md` (this file) |

### 2.3 Enforcement behavior to review

1. `ases_gate.py` verifies the adopted snapshot/lock/approval when a lock exists.
2. It validates Project Context sections, requirements, acceptance criteria and current milestone.
3. It requires the approved-decisions file referenced by the context to exist and be non-empty.
4. It requires `CURRENT_TASK.md` with `Status: Authorized` and explicit fields.
5. It rejects self-authorization, placeholders, project mismatch and invalid dates.
6. With `--changed-files`, it rejects paths outside `Files/modules allowed`.
7. With `--identity <file>`, it validates a separate task-identity record and reports its hash,
   without altering or bypassing the `CURRENT_TASK` authorization gate.
8. It is read-only and offline; exit codes are 0 pass, 1 blocked, 2 usage/error.

### 2.4 Identity Hash behavior to review

- Exactly nine identity fields; `schema_version = 3` validate-only; `risk_level` and
  `planned_task_id` excluded from the record and the payload.
- NFC normalization; `acceptance_criteria` ordered (no dedup); `depends_on` ordered (NFC then dedup
  keeping first occurrence); `required_capabilities`, `required_roles`, `execution_constraints`
  unordered sets (sort + dedup).
- Canonical JSON per RFC 8785 JCS (UTF-16 code-unit key ordering, JCS string escaping, UTF-8, no
  whitespace). SHA-256 output is lowercase 64-hex.
- Fail closed as `INVALID_CANONICAL_TASK` on missing/null/unknown/wrong-type/nested data and on an
  unsupported schema version.

### 2.5 Test evidence

Command: `python -m unittest discover -s tests -q`

Result at `5a57e2e`:

```text
Ran 131 tests in 40.302s
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
| Identity validation, canonicalization, hash | `test_ases_identity.py` (29 tests) |
| JCS key ordering, escaping, UTF-8 | `test_ases_identity.py` |
| schema_version integer type validation | `test_ases_identity.py` |

The single skip is `test_symlink_in_snapshot_rejected` because Windows did not permit symlink
creation locally; Windows junction rejection is tested and passes.

### 2.6 CI evidence

- Latest run for `5a57e2e`: `ASES policy files` check — success
  ([run 44856384408](https://github.com/tieucaca2004/AI-Software-Engineering-Standard/actions/runs/44856384408)).
- Earlier green runs exist for `7a569fb`, `6ff8b00` and prior commits.
- Required check: `ASES policy files`.
- Workflow steps: policy check, preflight, manifest check, full tests.

### 2.7 Security evidence

- `main-protection` ruleset active for `refs/heads/main`.
- Required approving reviews: 1.
- Require Code Owner review: yes.
- Required review thread resolution: yes.
- Strict required status checks: yes.
- Required context: `ASES policy files`.
- Bypass actors: `null` (none).
- No secrets or credentials found in the diff.
- No force-push or ruleset change performed; the only merge is PR #2 (Founder-authorized).

### 2.8 Known limitations reviewer must check

- The approval record is self-declared; it cannot prove a genuine Founder decision.
- Adopted-project CI is tested as a local CI-equivalent against a real temporary Git repository,
  not as a GitHub-hosted workflow in a separate repository.
- The gate cannot prove that an AI agent read or understood the documents.
- Hosted adoption CI and agent permissions are **NOT VERIFIED** independently.
- G6 Founder Acceptance for the Identity Hash feature is recorded but is feature-level only; it
  does not approve the whole ASES or release `VERSION 1.1.0`.

### 2.9 Reviewer focus checklist

1. Can any gate path produce PASS with missing/incomplete context, a non-authorized task,
   self-authorization or an out-of-scope changed file?
2. Does `--changed-files` parsing handle traversal, absolute paths, symlinks/junctions and
   unexpected file lists safely?
3. Does the approved-decisions file check resolve only project-relative paths and fail closed?
4. Does `ases_verify.py` verify all lock/manifest/version/approval relationships without a bypass?
5. Do all five adapters state the same mandatory behavior and failure response?
6. Does the adopted CI template actually fail a repository missing governance files, and does its
   diff step work on a real PR?
7. Does `ases_identity.py` implement the frozen contract exactly (fields, NFC, collection
   semantics, JCS, SHA-256, fail-closed) with no bypass?
8. Does `ases_gate.py --identity` validate the identity record without weakening the
   `CURRENT_TASK` authorization gate?
9. Are the docs honest about self-declared approval, reading limitations and unverified items?
10. Does the candidate remain within the approved five-component UAM scope?

## 3. PR #2 — CODEOWNERS (merged)

- Branch: `security/codeowners` (head `37cbdc6`).
- Merge commit: `6cffc35` on `main`.
- File: `.github/CODEOWNERS`, content `*  @tieucaca2004`.
- Verified on `main` (HTTP 200) and Code Owner review is active.

## 4. Identity status

- F1 and F2 (2026-11-18) are Founder-approved.
- The full Identity Hash contract — IDH-FIELDS, IDH-SEMANTICS, IDH-D01 through IDH-D04, and all
  remaining IDH-D05 rules — is Founder-approved (contract frozen at `73f392a`).
- Identity Hash is implemented and passed G6 Founder Acceptance (feature-level).
- RFC 8785 JCS compliance fix and the `schema_version` integer-type fix are included.
- G6 acceptance is feature-level only; it does not approve the whole ASES or release
  `VERSION 1.1.0`.

## 5. Review outcome handling

- Independent reviewer must record findings separately.
- The author does not approve or merge.
- Founder acceptance remains separate from any review.
- A passing CI run is not acceptance.
