# ASES Agent Authentication Adapter (Phase 1)

Canonical source for the ASES REV3 Phase 1 authentication adapter (`.ases-agent`).
This is the reference implementation of the request/result file mechanism (UQ16),
the interactive PAT flow (UQ1/UQ2), and the operation lifecycle (A3/A5).

## Status

- Phase 1 implementation complete; local/mock verification performed.
- Real-GitHub interactive verification: pending Founder run.
- `pr-create`: NOT AUTHORIZED (FDR-7 deferred). Exactly-once external effect: NOT PROVEN.

## Structure

| File | Purpose |
|---|---|
| `wrapper.ps1` | `ases-op` wrapper: allowlist/validation, request creation, single-writer ledger, concurrency lock, runner launch, result processing, cleanup |
| `runner.ps1` | interactive runner: request read, exclusive-create claim, SecureString PAT prompt, execution-intent marker (durable flush), identity verify, single-op execution, result write |
| `mock-gh.ps1` | isolated `gh` stub for local tests (no real GitHub/token) |
| `config/policy.json` | allowlist (6 ops), identity, timeouts |
| `tests/test-phase1.ps1` | local protocol verification harness |
| `tests/test-regression.ps1` | targeted cleanup-bug regression |
| `tests/test-durability.ps1` | controlled fault-injection (intent-flush then kill runner) |

## Deployment

At runtime the scripts use `%USERPROFILE%\.ases-agent\` as their root
(`run\`, `state\`, `state\ops\`, `config\`, `logs\`). Deploy by copying the
scripts into that directory.

## Design constraints (locked)

- Wrapper is the single writer of the authoritative ledger; the runner writes only
  `.claimed`, `.intent`, `.result`.
- The execution-intent marker is durably flushed before any external write.
- `UNKNOWN` is never auto-retried; evidence is retained for reconciliation.
- No credentials are persisted; the PAT is passed only via an interactive
  `Read-Host -AsSecureString` and held in-process.
