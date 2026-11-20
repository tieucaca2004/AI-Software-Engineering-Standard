# ASES Task Identity Contract — Provenance-Corrected Specification

**Status:** Documentation only. Identity Hash implementation is **not started**.
**Owner:** Founder retains approval and release authority.

This file separates three distinct categories of information and must not conflate them:

1. **Founder-approved decisions** (F1/F2 only).
2. **AI-recovered / proposed technical details** that have **not** been confirmed as
   Founder-approved.
3. **Unresolved technical details**.

It does not implement hashing and does not amend `CONSTITUTION.md` or F1/F2.

## 1. Founder-approved decisions — authoritative

Only the following are recorded as Founder-approved:

- **F1 (2026-11-18):** `risk_level` is excluded from the Identity Hash.
- **F1 (2026-11-18):** the Identity Hash uses exactly 9 identity fields.
- **F2 (2026-11-18):** `schema_version = 3` is kept.
- **F2 (2026-11-18):** no identity algorithm version is added.
- **IDH-D05 (2026-11-20):** `acceptance_criteria` is an ordered list; the order is preserved and
  duplicates are not removed.
- **IDH-D05 (2026-11-20):** `depends_on` is an ordered list; NFC normalization is applied first,
  then duplicates are removed while keeping the first occurrence.

The specific names of the nine fields are **not** part of the F1/F2 approval text above.

## 2. AI-recovered / proposed technical details — UNVERIFIED

**UNVERIFIED — NOT CONFIRMED AS FOUNDER-APPROVED.**

The following were supplied during remediation as recovered technical information. They are
retained for reference only. They have not been confirmed against an independent authoritative
source as Founder-approved. They must not be treated as a verified Founder contract.

### 2.1 Proposed identity fields (exactly nine)

1. `title`
2. `description`
3. `acceptance_criteria`
4. `required_capabilities`
5. `required_roles`
6. `scope`
7. `expected_output`
8. `execution_constraints`
9. `depends_on`

No tenth field is permitted by F1, but the exact nine names above remain unverified.

### 2.2 Proposed canonicalization rules

Founder-approved collection behavior (see section 1):

- `acceptance_criteria`: ordered list; order preserved; no de-duplication.
- `depends_on`: ordered list; NFC normalization first, then de-duplication keeping the first
  occurrence.

Remaining proposed rules (UNVERIFIED — NOT CONFIRMED AS FOUNDER-APPROVED):

- Object keys sorted in lexicographic order.
- `required_capabilities` and `required_roles` are unordered sets: sorted and de-duplicated.
- All strings use Unicode NFC.
- All nine keys must exist and must not be `null`.
- Empty values are represented explicitly as `""` or `[]`.
- Missing, null or invalid values return `INVALID_CANONICAL_TASK`; no automatic normalization or
  repair.
- `planned_task_id` is an output, not an input to the Identity Hash.

Note: `risk_level` exclusion is already Founder-approved by F1.

## 3. Unresolved technical details — Founder decision required

Identity hashing cannot be implemented until these are resolved:

1. Hash algorithm.
2. Final canonical payload structure immediately before hashing.
3. Whether `schema_version = 3` is included in the hash payload.
4. Byte serialization: encoding, separators and escaping.
5. Nested-value and data-type handling.

No values may be inferred for these items.

## 4. Relationship to the existing repository

- `scripts/ases_gate.py` contains `IDENTITY_FIELDS` for **project** identity (`Project name`,
  `Project ID`, `Repository`, `Primary branch`, `Owner`). Those are unrelated to this **task**
  identity contract and are not a conflict.
- The repository currently has no identity hash implementation.
- `CONSTITUTION.md` is unchanged.
- F1/F2 are unchanged.
- The UAM MVP remains exactly five components.
