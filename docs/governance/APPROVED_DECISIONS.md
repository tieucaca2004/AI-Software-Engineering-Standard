# APPROVED DECISIONS

Project: ASES REV3 ases-agent authentication adapter (Phase 1)
Last updated: 2026-11-22

This file records decisions explicitly approved by the Founder. It is not a place for AI assumptions.

| ID | Decision | Status | Approval date | Evidence / Reference |
|---|---|---|---|---|
| DEC-001 | Phase 1 scope is the ases-agent authentication adapter gap closure (runtime isolation, strict validation, result integrity, cleanup failure, credential lifecycle) | Accepted | 2026-11-22 | Founder task directives in the supervised development session |
| DEC-002 | result_sha256 field added to the REV3 result schema (§7.4.2 and §7.4.4) for result-content integrity | Accepted | 2026-11-22 | Founder authorization (Phase 1 final acceptance hardening) |
| DEC-003 | Strict UTC timestamp validation requires the ISO-8601 Z designator | Accepted | 2026-11-22 | Founder authorization (final protocol validation correction) |
| DEC-004 | pr-create is NOT AUTHORIZED for Phase 1 | Accepted | 2026-11-22 | Founder directive |
| DEC-005 | No commit or push during Phase 1 work until Founder authorization | Accepted | 2026-11-22 | Founder task directives |

## Locked constraints

- pr-create NOT AUTHORIZED; no commit/push during Phase 1; no UNKNOWN retry; production runtime untouched; FDR-7 deferred.

## Open proposals (not approved)

- Exactly-once operation guarantee (NOT PROVEN).
- FDR-7 external-write tests (DEFERRED).
- T25 permission-deny proof requiring a second account.

Rules:
- Proposed is not Approved.
- Silence is not approval.
- Changes require a Change Request and explicit Founder approval.
