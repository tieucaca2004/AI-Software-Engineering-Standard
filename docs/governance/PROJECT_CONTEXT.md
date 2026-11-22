# PROJECT CONTEXT

Project: ASES REV3 ases-agent authentication adapter (Phase 1)
Context version: 1
Last updated: 2026-11-22
Prepared by: DeepSeek agent under Founder supervision
Approved by: Founder
Approval evidence: Founder task directives in the supervised development session (2026-11-22)

## 1. Project Identity

- Project name: ASES REV3 ases-agent authentication adapter
- Project ID: ASES-REV3-PHASE1
- Repository: D:\AI\ASES-DeepSeek (GitHub tieucaca2004/AI-Software-Engineering-Standard)
- Primary branch: uam-mvp
- Owner: Founder

## 2. Business Problem and Users

- Problem: ASES REV3 requires the ases-agent adapter to authenticate an Agent's GitHub identity and scope before executing read-only operations, and to make every authentication, validation, tampering and cleanup failure path provably safe and evidenced.
- Users / stakeholders: Founder (owner/operator), the Agent invoking the adapter, and ASES REV3 adopters relying on the adapter's enforcement.
- Current process and pain: The adapter previously lacked strict JSON field-type validation, strict UTC timestamp validation, result-content integrity, and deterministic isolated cleanup-failure injection, which blocked Phase 1 acceptance evidence.
- Expected outcome: The adapter satisfies its authoritative REV3 requirements with isolated, non-secret, reproducible evidence for every mandatory criterion.
- Success measures: All local/isolated test cases EXECUTED PASS; production runtime untouched; both UNKNOWN records preserved and unretried.

## 3. Scope

### In scope

- ases-agent wrapper.ps1 and runner.ps1 Phase 1 gap closure.
- Isolated test harness and test scripts under enforcement/adapters/ases-agent/tests/.
- ASES REV3 Master specification changes directly required for Phase 1 (the result_sha256 field).
- Governance records under docs/governance/.

### Out of scope

- Universal-Orchestrator, Harness² and USHE changes.
- Exactly-once redesign and FDR-7 external-write implementation.
- Power-loss durability work beyond mandatory Phase 1 criteria.
- pr-create execution.
- Production runtime testing and real GitHub operations.

## 4. Requirements

| ID | Type | Requirement | Acceptance criteria | Status |
|---|---|---|---|---|
| REQ-001 | Functional | The wrapper and runner implement runtime isolation, strict request/result validation, result integrity, cleanup-failure handling and credential lifecycle per ASES REV3 | Isolated tests for each criterion execute and produce the required evidence | Approved |
| REQ-002 | Non-functional | Production runtime must remain untouched by all isolated testing and no secret values may appear in evidence | PRODUCTION-ISOLATION reports prod_files_changed=0 and secret scan reports no real PAT | Approved |
| REQ-003 | Functional | Strict UTC timestamp validation requires the ISO-8601 Z designator and rejects non-UTC offsets, missing timezone, invalid dates and malformed values | Offset, no-timezone, invalid-date and malformed inputs exit non-zero while valid Z inputs exit 0 | Implemented |
| REQ-004 | Non-functional | Result-content integrity via result_sha256 detects modified fields while preserving the documented limitation that an unkeyed hash does not authenticate against an actor who can recompute it | Modified result with preserved hash is rejected; recomputed-hash case is accepted and documented | Implemented |

## 5. Architecture and Data

- Data storage: Filesystem ledger under the runtime root (state/ops per op_id) and run/ artifacts (request, result, claim, intent); no database.
- API/integration: GitHub CLI (gh) read-only API for whoami, repo-permissions, pr-list, pr-view and pr-checks.
- Authentication/authorization: Interactive PAT via Read-Host -AsSecureString; identity and scope verification against policy.json (login chautinhtinh3979, scope repo).
- Error handling: Error categories per REV3 §9.1 (AUTH_MISSING, VALIDATION, CLEANUP_FAILURE and others); fail-closed; UNKNOWN never auto-retried.
- Deployment: Local PowerShell 5.1 wrapper/runner; production runtime default %USERPROFILE%\.ases-agent.
- Backup/recovery: N/A (no persistent datastore beyond the local ledger; recovery follows REV3 reconciliation rules)
- Architecture decisions / ADR references: ASES REV3 Master (C:\Users\phong\Documents\ASES\ASES-Agent-Authentication-Architecture-Rev3.md); decisions A1-A7 and FDR-1 through FDR-12.
- Data lifecycle, migration and retention: Request/result/claim/intent files are removed after processing; ledger records are retained as acceptance evidence; UNKNOWN records are preserved and never retried.

## 6. Security and Quality

- Secrets: No PAT, token, Authorization header or credential value is written to source, logs or evidence; test PATs are clearly-labeled non-secret fakes.
- Permissions: Production runtime and test roots use fail-closed isolation guards (sentinel and reparse-point rejection).
- Input validation: Strict JSON (65,536-byte limit, UTF-8 no BOM, duplicate-key rejection, exact key set, field-type and UTC timestamp enforcement).
- Audit logging: Ledger records per operation (op_id, state, hashes, cleanup_status, notes); non-secret.
- Dependency and supply-chain risk: N/A (adapter is PowerShell 5.1 with no third-party dependencies)
- Test strategy summary: Isolated harness invokes the canonical wrapper only; mock gh for local behavior; Founder interactive for real-GitHub.
- Known security limitations: Same-account tampering is not prevented (documented); exactly-once is not proven; FDR-7 external-write tests are deferred.

## 7. Delivery Plan

- Milestones: Phase 1 (ases-agent gap closure) is in progress; subsequent phases (Universal-Orchestrator, Harness²) are out of scope.
- Test strategy: Isolated harness plus targeted test scripts (strict JSON, result integrity, size boundaries, timestamp, canonicalization) with preserved evidence.
- Risks: Founder-dependent tests (T03/T26 interactive, permission-deny, real-GitHub) remain unexecuted; commit/push is prohibited by the current task directive and conflicts with AGENTS.local.md.
- Dependencies: Founder interactive real-GitHub verification for T01/T04/T21.
- Rollback plan: N/A (no commit/push performed; working tree preserved as-is)
- Evidence required at each gate: EXECUTED PASS/FAIL with exit codes and evidence paths; production isolation; secret scan.

## 8. Current Milestone

- Milestone ID: ASES-REV3-PHASE1
- Objective: Close the ases-agent Phase 1 gap (strict validation, result integrity, cleanup failure, credential lifecycle) and produce acceptance evidence.
- Authorized scope: enforcement/adapters/ases-agent/** and docs/governance/** only.
- Acceptance criteria: Every mandatory REV3 criterion has EXECUTED evidence at the required level; production runtime untouched; UNKNOWN records preserved; Phase 1 is not accepted until Founder real-GitHub verification and approval.
- Status: In Progress
- Target date: Pending Founder real-GitHub verification
- Evidence location: enforcement/adapters/ases-agent/tests/*.ps1 and preserved %TEMP%\ases-* isolated roots.

## 9. Founder Decisions

- Approved decisions: docs/governance/APPROVED_DECISIONS.md
- Locked constraints: pr-create NOT AUTHORIZED; no commit/push during Phase 1; no UNKNOWN retry; production runtime untouched; FDR-7 deferred.
- Open proposals (not approved): exactly-once operation guarantee; FDR-7 external-write tests; T25 permission-deny proof.
- Exceptions approved by the Founder: result_sha256 field added to the REV3 result schema (§7.4.2 and §7.4.4).

Rules: a proposal is not approval; silence is not approval; a task record does not grant scope beyond this context. Changes to approved decisions require a Change Request and explicit Founder approval.
