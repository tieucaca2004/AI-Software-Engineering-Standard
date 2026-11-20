# ASES Task Identity Contract — Final Unified Specification

**Status:** Unified technical contract for Founder review. Identity Hash implementation is **not
started**.
**Owner:** Founder retains approval and release authority.

This document is the single source of truth for the task-identity contract. It separates:

1. **FOUNDER-APPROVED** decisions.
2. **PROPOSED — PENDING FOUNDER APPROVAL** technical details.
3. No other categories.

## 1. FOUNDER-APPROVED

- **F1 (2026-11-18):** `risk_level` is excluded from the Identity Hash.
- **F1 (2026-11-18):** the Identity Hash uses exactly 9 identity fields.
- **F2 (2026-11-18):** `schema_version = 3` is kept.
- **F2 (2026-11-18):** no identity algorithm version is added.
- **IDH-D05 (2026-11-20):** `acceptance_criteria` is an ordered list; order is preserved; no
  de-duplication.
- **IDH-D05 (2026-11-20):** `depends_on` is an ordered list; NFC normalization first, then
  de-duplication keeping the first occurrence.

## 2. PROPOSED — PENDING FOUNDER APPROVAL

The items below are final technical proposals. They are **not** Founder-approved until the Founder
explicitly confirms them.

### 2.1 Identity fields (exactly nine)

1. `title`
2. `description`
3. `acceptance_criteria`
4. `required_capabilities`
5. `required_roles`
6. `scope`
7. `expected_output`
8. `execution_constraints`
9. `depends_on`

### 2.2 Identity semantics

Identity Hash represents **task content**, not a task instance. Two tasks with identical identity
content produce the same hash regardless of task ID, assignment, `risk_level`, or
`planned_task_id`.

### 2.3 Field type contract

| Field | Type | Semantics | Status |
|---|---|---|---|
| `title` | string | Required; NFC | PROPOSED |
| `description` | string | Required; NFC | PROPOSED |
| `acceptance_criteria` | string[] | Ordered list; keep order; no dedup | **FOUNDER-APPROVED** |
| `required_capabilities` | string[] | Unordered set; sort + dedup after NFC | PROPOSED |
| `required_roles` | string[] | Unordered set; sort + dedup after NFC | PROPOSED |
| `scope` | string | Required; NFC | PROPOSED |
| `expected_output` | string | Required; NFC | PROPOSED |
| `execution_constraints` | string[] | Unordered set of independent constraints; sort + dedup after NFC | PROPOSED |
| `depends_on` | string[] | Ordered list; NFC then dedup keeping first occurrence | **FOUNDER-APPROVED** |

### 2.4 Validation rules

- Exactly the nine keys; no missing keys; no unknown top-level keys.
- No `null`; no nested objects; no wrong types; string arrays contain only strings.
- Empty `""` and empty `[]` are valid for a correctly typed field.
- NFC normalization is applied before string comparison and collection processing.
- Any validation error returns `INVALID_CANONICAL_TASK`; fail closed; no automatic repair beyond
  the specified normalization steps.

### 2.5 Hash algorithm

- SHA-256.
- Output: lowercase hexadecimal, exactly 64 characters.

### 2.6 Canonical payload

- The canonical payload contains only the nine identity fields.
- It excludes `risk_level`, `planned_task_id`, and `schema_version`.
- Identity data is stored in a **separate identity record**, not merged into the `CURRENT_TASK`
  authorization record. The linking mechanism between the identity record and the task
  authorization record must be defined during implementation without changing `CURRENT_TASK`
  semantics.

### 2.7 `schema_version` behavior

- `schema_version = 3` is validation-only; it is not part of the hash payload.
- An unsupported schema version is rejected.
- Any change to field semantics or serialization requires a migration/compatibility policy and
  Founder approval.
- No identity algorithm version is added.

### 2.8 Canonical serialization

1. NFC-normalize every string before serialization.
2. Serialize the nine-field object using **RFC 8785 JSON Canonicalization Scheme (JCS)** with
   JCS key ordering, JCS string escaping, no insignificant whitespace, and no trailing newline.
3. Encode as UTF-8.
4. Do not modify the JCS algorithm. Input-type restrictions are applied at the validation layer,
   not inside serialization. Do not claim RFC 8785 compliance unless the implementation satisfies
   RFC 8785.

## 3. Hash flow

1. Receive the Task Identity Record.
2. Validate `schema_version` (`3`).
3. Validate the nine fields, keys and types.
4. NFC-normalize all strings.
5. Apply per-field collection semantics.
6. Build an object containing only the nine identity fields.
7. Canonicalize with RFC 8785 JCS.
8. Encode UTF-8.
9. Compute `SHA-256` over the canonical bytes.
10. Emit a lowercase 64-character hexadecimal digest.

Any validation error stops before hashing.

## 4. Relationship to the existing repository

- `scripts/ases_gate.py` `IDENTITY_FIELDS` are **project** identity fields, unrelated to task
  identity.
- The repository currently has no identity-hash implementation.
- `CONSTITUTION.md` is unchanged.
- F1/F2 are unchanged.
- The UAM MVP remains exactly five components.
