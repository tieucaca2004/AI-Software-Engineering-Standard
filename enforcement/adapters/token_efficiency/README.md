# ASES Token Efficiency — Budget Evaluator & Decision Evidence

Procedural budget control for ASES REV3. Evaluates prepared provider-reported usage
against a budget policy and records an `ases-budget-decision/1`. This is a
**workflow-level control, not an ASES Core hard gate**, and provides **no runtime token
enforcement**.

## Components

| Module | Purpose |
|---|---|
| `policy.py` | `ases-budget-policy/1` representation + validation (`validate_policy`, `total_tokens_from_usage`) |
| `evaluator.py` | deterministic `evaluate(policy, usage_input, policy_ref)` → decision record |
| `decision.py` | `ases-budget-decision/1` schema + `validate_decision` |
| `cli.py` | workflow CLI (`--policy --usage --output`) |

## Budget policy (`ases-budget-policy/1`)

```json
{ "schema": "ases-budget-policy/1", "policy_id": "p1", "policy_version": "1",
  "scope": "work-unit", "metric": "tokens",
  "warning_threshold": 100000, "block_threshold": 200000 }
```
- `scope` ∈ `work-unit | request`; `metric` ∈ `tokens | cost`.
- At least one threshold required; `warning_threshold <= block_threshold`.
- No default amounts/currencies are invented; missing/contradictory values are rejected, not defaulted permissively.

## Evaluator input contract (M4 supplies this)

```json
{ "scope": "work-unit", "work_unit_id": "wu-1", "completeness": "complete",
  "total_tokens": 33820, "total_cost_usd": 0.078, "evidence_refs": ["usage-1.json"] }
```
The evaluator does **not** aggregate raw records (that is M4). It consumes an already
prepared usage total/snapshot.

## Decision semantics

| Decision | Meaning | admits_next |
|---|---|---|
| `ALLOW` | usage within budget | true |
| `WARN` | at/above warning, below block | true |
| `BLOCK` | at/above block | false |
| `UNAVAILABLE` | cannot determine (missing/invalid/partial usage) | false |

- Only `completeness=complete` usage drives a definitive decision; `partial`/`unavailable`
  usage → `UNAVAILABLE` (never `ALLOW`).
- `UNAVAILABLE` never silently becomes `ALLOW`.

## Workflow admission procedure

```
Previous Work Unit → usage evidence → evaluator → decision evidence persisted → admission
```
- `ALLOW`/`WARN` → admit next Work Unit (WARN is recorded).
- `BLOCK` → stop admission, persist decision, escalate.
- `UNAVAILABLE` → do not proceed without an explicit, recorded override.
- An override must carry `authorized_by` and `scope`; it is never fabricated or auto-generated.

## Failure behavior

Missing/invalid policy or usage, unreadable evidence, or evaluator exceptions all produce
`UNAVAILABLE` (never `ALLOW`); a decision/evidence persistence failure is surfaced, never
silently discarded. Provider-reported usage is never conflated with independently verified
facts. No automatic retry of UNKNOWN.

## Limitations

- Procedural enforcement only: an operator can technically bypass the workflow; no Core-level
  enforcement is claimed.
- No runtime token enforcement.
- Aggregation/dedup/conflict-resolution is M4 (out of scope here).

## Testing

`tests/` — `test_policy.py`, `test_evaluator.py`, `test_decision.py`, `test_workflow.py`.
