# ASES REV3 — PHASE 1 CONSOLIDATED EVIDENCE

Project: ASES REV3 ases-agent authentication adapter (Phase 1)
Status: **NOT ACCEPTED** (pending Founder real-GitHub verification and acceptance)
Last updated: 2026-11-22
Prepared by: DeepSeek agent under Founder supervision

## 1. Completed Work Units

| Work Unit | Track | Objective | Files changed | Result |
|---|---|---|---|---|
| WU-1 (T17) | Adapter | Harness T17 real cleanup-failure fault injection | `tests/isolated-harness.ps1` | **EXECUTED PASS** (inject exit 6, blocker, reject exit 23) |
| WU-2 (README) | Adapter | Document hooks/strict validation/result_sha256/inventory | `README.md` | **EXECUTED PASS** (cross-checked against source) |
| WU-LEGACY-GUARD | Adapter | Fail-closed production guard on 5 legacy test scripts | 5 × `tests/test-*.ps1` | **EXECUTED PASS** (exit 90 REFUSE, production untouched) |
| WU-T03-EMPTYPAT | Adapter | T03 empty-PAT injection + `$tmpCfg` null fix | `runner.ps1`, `wrapper.ps1`, `isolated-harness.ps1` | **EXECUTED PASS** (AUTH_MISSING) |
| Gate bullet-parser fix | Core | Repair multiline bullet regex (`re.MULTILINE`) | `scripts/ases_gate.py` | **EXECUTED PASS** (59 gate tests) |
| Per-Work-Unit baseline | Core | Hash-based baseline snapshot + delta isolation | `scripts/ases_gate.py` | **EXECUTED PASS** (B01–B20) |
| B12/B16 fail-closed + bypass prevention | Core | Repo-identity guard; mandatory scope evidence | `scripts/ases_gate.py` | **EXECUTED PASS** (172 tests) |
| Governance records | Governance | PROJECT_CONTEXT / CURRENT_TASK / APPROVED_DECISIONS | `docs/governance/*` | Gate PASS |

## 2. Governance Mechanism Status

| Mechanism | Status |
|---|---|
| Task Gate (`ases_gate.py check`) | **PASS** (governed work units require `--baseline`, `--changed-files`, or explicit `--legacy-collect`) |
| Per-Work-Unit baseline + delta | **Operational** (hash-based snapshot; fails closed on non-own-repo) |
| Scope enforcement | **Mandatory** (out-of-scope → `TASK_SCOPE_VIOLATION` BLOCK) |
| Policy (`check_policy.py`) | **PASS** |
| Manifest (`ases_verify.py manifest --check`) | **current (25 files)** |

## 3. Adapter Test Evidence (isolated/mock)

| Area | Result |
|---|---|
| T01/T02/T04/T05/T16/T17/T21 | **PASS** |
| T03 empty PAT | **PASS** (isolated injection) |
| T25 request/result tamper, strict JSON, size, timestamp | **EXECUTED PASS** (dedicated scripts) |
| T26 two-op / invalid / different credential / interruption / no residual GH_TOKEN | **PASS** |
| Result integrity (result_sha256) + canonicalization | **EXECUTED PASS** |
| PRODUCTION-ISOLATION | **PASS** (`prod_files_changed=0`) |
| Full Python suite | **172 tests OK (skipped=1)** |

## 4. Remaining Blockers (Founder-dependent)

- Real-GitHub verification: T01 identity, T04 401, T21 expiry header.
- Interactive verification: real PAT prompt per op, window-cancel, prompt-timeout.
- T25 permission-deny (requires a second Windows account).
- Exactly-once external effect: **NOT PROVEN**.
- FDR-7 external-write tests: **DEFERRED**.
- `pr-create`: **NOT AUTHORIZED**.
- `milestone-1.diff` disposition (untracked diff artifact, not in authorized scope).
- Commit/push conflict (`AGENTS.local.md` requires commit; Phase 1 directives prohibit) — pending Founder resolution.

## 5. Evidence Locations

- Adapter tests: `enforcement/adapters/ases-agent/tests/*.ps1` + preserved `%TEMP%\ases-*` isolated roots.
- Governance records: `docs/governance/`.
- UNKNOWN records (preserved, unretried): `a3f1988e-b02e-4d85-9c4b-3364edb665ac`, `1d624876-2500-42c8-a949-6edb1270eff2`.

## 6. Status

**Phase 1 NOT ACCEPTED.** All local/isolated Core and adapter objectives are complete with executed evidence; acceptance requires the Founder's real-GitHub interactive verification and formal approval.
