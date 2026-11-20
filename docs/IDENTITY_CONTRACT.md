# ASES Task Identity Contract — Recovered Specification

**Status:** Documentation only. Identity hash implementation is **not started**.
**Source:** Founder-provided contract recovery (2026-11-20 remediation); F1/F2 approved 2026-11-18.
**Owner:** Founder retains approval and release authority.

This file records the recovered task-identity contract and its canonicalization rules. It
separates recovered items from the technical details that remain unresolved. It does not implement
hashing and does not amend the Constitution or F1/F2.

## 1. Identity fields — exactly nine

1. `title`
2. `description`
3. `acceptance_criteria`
4. `required_capabilities`
5. `required_roles`
6. `scope`
7. `expected_output`
8. `execution_constraints`
9. `depends_on`

No tenth field is permitted.

## 2. Canonicalization rules — recovered

- Object keys are sorted in lexicographic order.
- `acceptance_criteria`, `required_capabilities` and `depends_on` are sets: sorted and
  de-duplicated.
- All strings use Unicode NFC.
- All nine keys must be present and must not be `null`.
- Empty values must be represented explicitly as `""` or `[]`.
- Missing, null or invalid values return `INVALID_CANONICAL_TASK`. No automatic normalization or
  repair is performed.
- `risk_level` is excluded from the Identity Hash; it is for display/audit only.
- `planned_task_id` is an output, not an input to the Identity Hash.
- `schema_version = 3` must be preserved; no identity algorithm version is added.

## 3. Unresolved technical details — Founder decision required

The following are not yet specified and therefore identity hashing cannot be implemented:

1. Hash algorithm.
2. Final canonical payload structure immediately before hashing.
3. Whether `schema_version = 3` is included in the hash payload.
4. Byte serialization: encoding, separators and escaping.
5. Nested value and type handling.

No values may be inferred for these items.

## 4. Relationship to the existing repository

- `scripts/ases_gate.py` contains `IDENTITY_FIELDS` for **project** identity (`Project name`,
  `Project ID`, `Repository`, `Primary branch`, `Owner`). Those are unrelated to this **task**
  identity contract and are not a conflict.
- The repository currently has no identity hash implementation.
- `CONSTITUTION.md` is unchanged.
- F1/F2 are unchanged.
- The UAM MVP remains exactly five components.
