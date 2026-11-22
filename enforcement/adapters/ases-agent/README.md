# ASES Agent Authentication Adapter (Phase 1)

Canonical source for the ASES REV3 Phase 1 authentication adapter (`.ases-agent`).
This is the reference implementation of the request/result file mechanism (UQ16),
the interactive PAT flow (UQ1/UQ2), and the operation lifecycle (A3/A5).

## Status

- Phase 1 implementation complete; local/mock verification performed.
- Strict JSON field-type validation, strict UTC timestamp validation, result-content
  integrity (`result_sha256`), and isolated fault-injection hooks are implemented and
  exercised by the isolated test suite.
- Real-GitHub interactive verification: pending Founder run.
- `pr-create`: NOT AUTHORIZED (FDR-7 deferred). Exactly-once external effect: NOT PROVEN.

## Structure

| File | Purpose |
|---|---|
| `wrapper.ps1` | `ases-op` wrapper: allowlist/validation, strict request creation, single-writer ledger, concurrency lock, runner launch, strict result validation (`result_sha256`), cleanup |
| `runner.ps1` | interactive runner: strict request validation, exclusive-create claim, SecureString PAT prompt, execution-intent marker (durable flush), identity verify, single-op execution, result write with `result_sha256` |
| `mock-gh.ps1` | isolated `gh` stub for local tests (no real GitHub/token) |
| `config/policy.json` | allowlist (6 ops), identity, timeouts |
| `tests/isolated-harness.ps1` | canonical isolated test harness (fresh `%TEMP%` runtime root, invokes wrapper only) |
| `tests/test-rfc8785.ps1` | canonicalization fixed vectors |
| `tests/test-type-enforce.ps1` | strict field-type / duplicate-key / UTF-8 / size regression |
| `tests/test-result-integrity.ps1` | result-integrity (`result_sha256`) tamper matrix |
| `tests/test-size-ts.ps1` | exact size-boundary and UTC timestamp validation |
| `tests/test-final-gaps.ps1` | result-size boundary and duplicate result-key cases |
| `tests/test-final-verify.ps1` | direct-runner security and strict-validation vectors |
| `tests/test-gap-closure.ps1` | T17 cleanup-failure injection and T25 request-tamper |
| `tests/test-phase1.ps1`, `test-regression.ps1`, `test-durability.ps1`, `test-gaps.ps1`, `test-f1f5.ps1` | legacy targeted tests (see notes below) |

## Runtime isolation (fail-closed)

- Production root is `%USERPROFILE%\.ases-agent\` (`run\`, `state\`, `state\ops\`, `config\`, `logs\`).
- `ASES_AGENT_ROOT` overrides the runtime root for isolated tests. It is validated
  fail-closed: must differ from the production root, carry the `.ases-agent-test-root`
  sentinel (a real file, not a reparse point), and contain the required subdirectories;
  any reparse-point/junction/symlink in the path is rejected.
- The runner independently re-validates the root (reads `ASES_AGENT_ROOT`) and rejects
  the production root whenever a test override is active — direct runner invocation
  cannot bypass isolation.
- Mock `gh` fault injection: `MOCK_LOGIN`, `MOCK_SCOPE`, `MOCK_TOKEN_EXPIRY`,
  `MOCK_AUTH_FAIL=401`, `MOCK_NETWORK_FAIL`, `MOCK_HTTP_FAIL`, `MOCK_SLEEP_SECONDS`.

## Test-only fault-injection hooks (isolated root only)

These hooks are gated fail-closed: they activate only when `ASES_AGENT_ROOT` is set to a
validated isolated test root and are no-ops when unset (production behavior unchanged).

| Hook | Effect |
|---|---|
| `ASES_TEST_CLEANUP_FAIL=1` | forces the wrapper cleanup to fail once → `CLEANUP_FAILURE`, `state\cleanup_failed` blocker, subsequent operations rejected |
| `ASES_TEST_PAUSE_AFTER_REQUEST=1` | pauses after the request hash is recorded, before the runner launches (request-tamper window) |
| `ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE=1` | pauses after the runner writes the result, before the wrapper validates it (result-tamper window) |

## Strict validation

- Request and result files are limited to 65,536 UTF-8 bytes (no BOM).
- Duplicate JSON keys are rejected at every nesting level (structural scan that decodes
  escaped names); unknown keys and missing required keys are rejected (case-sensitive).
- Field types, enums, UUID v4 `op_id`, 64-hex SHA-256 fields, and ISO-8601 UTC timestamps
  (literal `Z` required; non-UTC offsets, missing timezone and date-only rejected;
  fractional seconds permitted) are enforced at the wrapper/runner trust boundaries.
- Result integrity: the runner writes `result_sha256` = SHA-256 over the canonical
  (RFC-8785-style, ordinal key order) serialization of the result excluding the hash
  field; the wrapper independently re-canonicalizes and re-verifies. This detects
  modified fields but does not authenticate against an actor able to change both
  content and hash (documented limitation).

## Deployment

At runtime the scripts use `%USERPROFILE%\.ases-agent\` as their root. Deploy by copying
the scripts into that directory.

## Design constraints (locked)

- Wrapper is the single writer of the authoritative ledger; the runner writes only
  `.claimed`, `.intent`, `.result`.
- The execution-intent marker is durably flushed before any external write.
- `UNKNOWN` is never auto-retried; evidence is retained for reconciliation.
- No credentials are persisted; the PAT is passed only via an interactive
  `Read-Host -AsSecureString` and held in-process.
- Cleanup failures are propagated separately (never silently swallowed) and activate the
  `cleanup_failed` blocker.
