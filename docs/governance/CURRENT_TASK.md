# CURRENT TASK

- Task ID: ASES-REV3-PHASE1-GOV
- Project: ASES-REV3-PHASE1
- Agent: DeepSeek agent
- Requested by: Founder
- Date: 2026-11-22
- Status: Authorized
- Objective: Reconcile the task authorization with the actual Founder-authorized Phase 1 work and implement mandatory interactive scope enforcement in the ASES-DeepSeek governance workflow.
- Authorized scope: Reconcile docs/governance/CURRENT_TASK.md with the cumulative Founder-authorized Phase 1 scope; extend scripts/ases_gate.py to collect actual changed files and enforce scope when the caller does not supply --changed-files; extend tests/test_ases_gate.py; regenerate ases-manifest.json for the legitimately modified managed file.
- Files/modules allowed: docs/governance/**, enforcement/adapters/ases-agent/**, scripts/ases_gate.py, tests/test_ases_gate.py, ases-manifest.json
- Prohibited actions: No production runtime access; no GitHub or credential access; no commit or push; no Constitution or APPROVED_DECISIONS modification; no UNKNOWN retry or modification; no deletion of existing evidence; no modification of milestone-1.diff.
- Implementation requirements: Record only established facts and Founder-approved decisions; preserve Phase 1 NOT ACCEPTED, Founder-dependent tests PENDING, exactly-once NOT PROVEN, FDR-7 DEFERRED and pr-create NOT AUTHORIZED.
- Testing requirements: Run python scripts\ases_gate.py check --project-root .; run scripts\check_policy.py and scripts\ases_verify.py manifest --check; run python -m unittest discover -s tests.
- Acceptance criteria: Scope enforcement is mandatory when changed-file information is available; in-scope changes PASS and out-of-scope changes BLOCK; existing tests continue to pass; manifest remains current.
- Approved decisions reference: docs/governance/APPROVED_DECISIONS.md
- Authorization evidence: Founder task directive "ASES REV3 — AUTHORIZATION RECONCILIATION & INTERACTIVE SCOPE ENFORCEMENT" (2026-11-22)

## Notes

- `milestone-1.diff` is an untracked diff artifact at the repository root, not a source change; it is intentionally NOT covered by the authorized scope and is therefore flagged as out-of-scope by the gate (pending a separate Founder disposition).
- `Files/modules allowed` is enforced when the gate runs with collected or supplied changed files.
- Do not edit this record to widen scope beyond what the Founder authorized.
- A commit, a passing check or silence is not Founder acceptance.
