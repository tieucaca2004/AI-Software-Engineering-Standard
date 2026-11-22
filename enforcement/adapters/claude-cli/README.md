# Claude CLI Adapter (ASES Agent Provider Contract)

First provider adapter for the ASES Agent Provider Contract. Translates
`ases-exec-request/1` into a `claude -p` invocation and normalizes the outcome into
`ases-exec-result/1`.

## Responsibilities

- Provider identity + capability reporting.
- Request validation against the standardized contract.
- Command construction (`claude -p --output-format json` + model/permission/tool flags).
- Process lifecycle (timeout/interruption).
- Output/evidence/error classification.
- `ases-exec-result/1` result generation.

## Boundaries (do not conflate)

- **ASES governance/scope** — post-execution delta/scope verification (authoritative).
- **Claude permission modes** — provider-level policy, not OS isolation.
- **OS filesystem isolation** — not provided by this adapter (no sandbox/interceptor).

The adapter never self-authorizes; it never proves authorization authenticity; it never
auto-retries UNKNOWN; it never guarantees process-tree termination (children may orphan).

## Configuration

`config.json`: `executable` (default `claude`), `timeout_seconds` (default 600), `model`,
`permission_mode`. No credentials are stored.

## Usage collection (ases-usage/1)

The adapter parses the Claude CLI `--output-format json` output and normalizes provider-reported
usage into `ases-usage/1` (accessible as `adapter.last_usage`; persisted as `adapter.last_usage_ref`).

| Provider field | `ases-usage/1` field |
|---|---|
| `usage.input_tokens` | `input_tokens` |
| `usage.output_tokens` | `output_tokens` |
| `usage.cache_creation_input_tokens` | `cache_creation_input_tokens` |
| `usage.cache_read_input_tokens` | `cache_read_input_tokens` |
| `usage.output_tokens_details.thinking_tokens` | `thinking_tokens` (optional) |
| `total_cost_usd` (top-level) | `total_cost_usd` (optional) |

- `complete` = all four core metrics non-null; `partial` = ≥1 core non-null; `unavailable` = all four core null.
- Zero is a reported value; null means not reported. Missing metrics are never fabricated/estimated.
- `thinking_tokens` and cache breakdowns are not double-counted into core metrics.
- Usage collection failure does **not** change the execution `status` (independent axes).
- **Known limitation:** exact `input_tokens`-vs-cache semantics are inferred from observed output;
  `modelUsage`/`server_tool_use`/iteration metadata are treated as informational breakdowns, not core usage.
- **Real-provider verification:** VERIFIED (real `claude -p` usage extracted, validated, attributed).

## Testing

- `tests/test_claude_adapter.py` — unit + mocked-process lifecycle tests.
- `tests/test_usage_parsing.py` — usage parsing/normalization tests.
- Real `claude -p` integration is executed when authentication is available; mocked tests are not
  reported as real-provider verification.
