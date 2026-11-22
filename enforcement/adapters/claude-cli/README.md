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

## Testing

- `tests/test_claude_adapter.py` — unit + mocked-process lifecycle tests.
- Real `claude -p` integration is **Founder-dependent** (requires Claude authentication);
  it is NOT substituted by mocks.
