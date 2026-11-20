# ASES Founder Identity Decisions — Technical Option Package

**Status:** Decision package for Founder review. All “Recommended” entries are **AI proposals**, not
Founder-approved decisions. No implementation is authorized by this document.

**Related:** `docs/IDENTITY_CONTRACT.md` (provenance-corrected specification).

## 1. Approved decisions (authoritative)

Only these are Founder-approved (2026-11-18):

- **F1:** `risk_level` is excluded from the Identity Hash.
- **F1:** the Identity Hash uses exactly 9 identity fields.
- **F2:** `schema_version = 3` is kept.
- **F2:** no identity algorithm version is added.

## 2. Current architecture and gaps

### Current implementation behavior

- No identity-hash code exists in the repository.
- `scripts/ases_gate.py` validates a `CURRENT_TASK` authorization record with fields:
  `Task ID`, `Project`, `Agent`, `Requested by`, `Date`, `Status`, `Objective`,
  `Authorized scope`, `Files/modules allowed`, `Prohibited actions`,
  `Implementation requirements`, `Testing requirements`, `Acceptance criteria`,
  `Approved decisions reference`, `Authorization evidence`.
- `IDENTITY_FIELDS` in `scripts/ases_gate.py` are **project** identity fields
  (`Project name`, `Project ID`, `Repository`, `Primary branch`, `Owner`), not task identity.
- The existing manifest/lock verifier uses SHA-256 with canonicalization `text-lf-v1`; that is
  unrelated to task identity.

### Contract gaps

1. The nine proposed identity fields (`title`, `description`, `acceptance_criteria`,
   `required_capabilities`, `required_roles`, `scope`, `expected_output`,
   `execution_constraints`, `depends_on`) do not yet exist in any task record in the repository.
2. No canonical payload, serialization or hash rule is defined.
3. No decision on where the nine fields are stored (extend `CURRENT_TASK`, a new task-identity
   record, or another location) has been made.
4. No identity invariance or negative tests exist.

## 3. Decision items

Each item has a unique ID, options, a recommendation (proposal), an example, expected tests and
the question for the Founder.

### IDH-D01 — Hash algorithm

**Gap:** the hash function is unspecified.

| Option | Pros | Cons / risk |
|---|---|---|
| SHA-256 | Standard, collision-resistant, `hashlib`, consistent with existing snapshot hashes | None material for this use |
| BLAKE2b-256 | Fast, modern | Less tooling familiarity; no need over SHA-256 |
| SHA3-256 | Sponge-based alternative | Slower; unnecessary divergence |

**Recommended (proposal):** SHA-256, lowercase 64-hex output.

**Example:**

```text
identity_hash = sha256(canonical_bytes)
```

**Expected tests:** same input → same digest; known-vector test; deterministic output.

**Founder question:** confirm SHA-256.

---

### IDH-D02 — Canonical payload structure

**Gap:** the exact top-level structure before hashing is unspecified.

| Option | Pros | Cons / risk |
|---|---|---|
| A. Hash only the 9 identity fields (recommended) | Matches “exactly 9 fields”; stable | Requires separate handling of `schema_version` |
| B. Wrap the 9 fields with metadata | Explicit container | Adds fields beyond the 9 unless carefully separated |
| C. Include `planned_task_id` | Immutable binding | Violates F1 semantics if treated as identity input |

**Recommended (proposal):** Option A — a canonical JSON object containing only the nine identity
fields, sorted lexicographically by key. `risk_level` and `planned_task_id` are excluded from the
object. `schema_version` is handled by IDH-D03.

**Open prerequisite:** the source of the nine fields must be decided. Current `CURRENT_TASK`
fields differ from the proposed nine; the Founder must choose whether the identity record extends
`CURRENT_TASK`, becomes a new record, or is otherwise supplied.

**Example (values illustrative):**

```json
{"acceptance_criteria":["a","b"],"depends_on":[],"description":"demo","execution_constraints":[],
 "expected_output":"out","required_capabilities":["c"],"required_roles":["r"],"scope":"s","title":"t"}
```

**Expected tests:** all nine keys present; extra key handling; ordering independence.

**Founder question:** confirm Option A and choose where the nine fields are sourced.

---

### IDH-D03 — `schema_version` participation

**Gap:** whether `schema_version = 3` participates in the hash payload.

| Option | Pros | Cons / risk |
|---|---|---|
| A. Exclude from hash; validate only (recommended) | Hash remains exactly 9 fields; schema can evolve without invalidating identity | Weakens binding of an identity to a specific schema |
| B. Include in hash | Strong schema binding | Adds a tenth hash input, conflicting with F1 “exactly 9 fields” |

**Recommended (proposal):** Option A. Store `schema_version = 3` as record metadata used for
validation, not as hash input.

**Example:**

```json
{"schema_version": 3, "identity": {"title": "...", "...": "..."}}
```

Hash is computed only over `identity`.

**Expected tests:** changing `schema_version` does not change the hash; an unsupported
`schema_version` is rejected by validation.

**Founder question:** confirm Option A.

---

### IDH-D04 — Byte serialization

**Gap:** deterministic byte encoding is unspecified.

| Option | Pros | Cons / risk |
|---|---|---|
| A. RFC 8785 JSON Canonicalization Scheme (JCS) subset (recommended) | Standard, deterministic, well-understood | Slightly stricter rules |
| B. Custom compact JSON | Full control | Risk of unspecified escaping/whitespace rules |
| C. Separator-joined values | Simple | Ambiguous for arrays and Unicode |

**Recommended (proposal):** Option A — UTF-8 canonical JSON: no insignificant whitespace; keys
sorted lexicographically; minimal escaping; Unicode NFC normalization before serialization; no
trailing newline.

**Example (structured → canonical bytes):**

```text
Input:   {"title": "t", "scope": "s"}
Bytes:   7B 22 73 63 6F 70 65 22 3A 22 73 22 2C 22 74 69 74 6C 65 22 3A 22 74 22 7D
Text:    {"scope":"s","title":"t"}
```

**Expected tests:** whitespace variations produce identical bytes; key-order variations produce
identical bytes; NFC-equivalent Unicode produces identical bytes; escaping is deterministic.

**Founder question:** confirm RFC 8785 subset and UTF-8.

---

### IDH-D05 — Nested values and type rules

**Gap:** type and nested-value handling is unspecified.

| Option | Pros | Cons / risk |
|---|---|---|
| A. Strict scalars and string arrays only (recommended) | Fail-closed, unambiguous | Less expressive |
| B. Recursive nested objects | Expressive | More complexity and ambiguity |
| C. Ignore unknown keys | Tolerant | Risks two different records producing the same hash |

**Recommended (proposal):** Option A with:

- Allowed values: Unicode NFC strings; string arrays for `acceptance_criteria`,
  `required_capabilities`, `depends_on`.
- Numbers, booleans and nested objects are invalid in identity fields.
- `null` is invalid; empty is explicit `""` or `[]`.
- Arrays are sorted and de-duplicated.
- Missing/invalid → `INVALID_CANONICAL_TASK` (fail closed).
- Unknown top-level keys are rejected.

**Expected tests:** missing field, null, wrong type, empty string, empty array, duplicate array
items, nested object, unknown key, Unicode edge cases.

**Founder question:** confirm Option A and the rules above.

---

## 4. Identity stability analysis (under recommended options)

| Change | Expected behavior |
|---|---|
| Same 9 fields, same content | Same hash |
| `risk_level` changed | Hash unchanged (F1) |
| `planned_task_id` changed | Hash unchanged (output-only) |
| One identity field changed meaningfully | Hash changes |
| Object keys reordered | Same hash (canonical sort) |
| Set elements reordered | Same hash (sort) |
| Set duplicate removed | Same hash (deduplicate) |
| Unicode NFD → NFC equivalent | Same hash (normalize) |
| `schema_version` changed | Hash unchanged (Option A of D03) |

## 5. Expected acceptance test scenarios

1. **Stable Identity:** same task → same hash.
2. **Non-identity change:** change `risk_level` / `planned_task_id` → hash unchanged.
3. **Identity change:** change one identity field → hash changes.
4. **Invalid input:** missing/null/wrong-type → fail closed.
5. **Canonical equivalence:** key order, set order, NFC/NFD equivalence → correct per contract.

These become executable tests only after Phase C/D and after the Founder approves D01–D05.

## 6. Founder questions

- IDH-D01: confirm SHA-256.
- IDH-D02: confirm hash-only-9-fields payload and choose the field source.
- IDH-D03: confirm `schema_version = 3` is validation-only, not hash input.
- IDH-D04: confirm RFC 8785-subset canonical JSON, UTF-8, NFC.
- IDH-D05: confirm strict scalar/string-array rules and fail-closed behavior.

## 7. Stop condition

No code, schema, manifest or hash implementation is authorized until the Founder selects and
approves the IDH decisions above.
