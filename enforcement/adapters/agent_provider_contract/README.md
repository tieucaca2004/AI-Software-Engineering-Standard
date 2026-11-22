# ASES Agent Provider Contract

Provider-neutral integration contract between ASES Core and Agent Provider adapters.
This contract standardizes the adapter↔provider handoff only. It does **not** own
governance, authorization, orchestration, or policy. ASES Core remains the sole
authority for authorization, scope, and the final Work Unit result.

## Schemas

| Schema | Purpose |
|---|---|
| `ases-provider/1` | Provider identity + capability declaration |
| `ases-exec-request/1` | Execution request carrying Work Unit identity, authorization references, objective, scope, and provider config |
| `ases-exec-result/1` | Normalized execution result with independent execution / output / evidence outcomes |
| `ases-usage/1` | Token usage record (normalized provider-reported usage) |

## Key invariants

- **Three independent axes:** `status` (execution), `output_state` (output collection),
  `evidence_state` (evidence collection). Collection failure never relabels execution status.
- **Termination semantics:** `completed_utc` = natural completion; `terminated_utc` =
  observed termination (never implies the adapter initiated it); `termination_reason` ∈
  `none|start-failed|timeout|interrupted|external|lost-observability`; `termination_mechanism`
  is the kill method (required for adapter-initiated, optional for external, null otherwise).
- **UNKNOWN** (`lost-observability`) is never classified `INTERRUPTED` without termination
  evidence, never auto-retried, and never reports `evidence_state=complete`.
- **Fail-closed forward compatibility:** unknown execution-config fields are rejected
  (they may be constraining/security); unknown provider-identity fields are informational
  and ignored.
- **Authorization traceability:** the adapter verifies reference consistency; it does
  **not** grant authorization and does **not** prove authorization authenticity
  (established only by trusted invocation + post-execution ASES delta/scope).

## Validation

`validation.py` provides `validate_provider`, `validate_request`, `validate_result`,
and `validate_usage` (stdlib-only, deterministic). See `tests/test_contract.py` and
`tests/test_usage.py`.

## `ases-usage/1` semantics

- **Required core metrics:** `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`.
- **Optional metrics:** `thinking_tokens`, `total_cost_usd` (nullable without invalidating a complete record).
- **Completeness:** `complete` = all four core metrics non-null; `partial` = at least one (not all) core metric non-null; `unavailable` = all four core metrics null and `source=unavailable`.
- **Zero vs null:** `0` is a reported value; `null` means not reported.
- **Terminology:** use `complete provider-reported usage`, never `verified usage` (no independent verification exists).
