# IISE IMPLEMENTATION REPORT

Project: ASES REV3
Enhancement: Intent Integrity & Scope Enforcement (IISE)
Status: **IMPLEMENTED** (subsequent Core enhancement; does not retroactively alter Phase 1 acceptance)
Last updated: 2026-11-22

## 1. Existing Capabilities Reused

- `CURRENT_TASK.md` (authorized Work Unit, `Files/modules allowed`, objective, prohibited actions).
- `PROJECT_CONTEXT.md` (project objective/scope).
- `APPROVED_DECISIONS.md` (locked decisions).
- Existing `ases_gate.py` gate/scope/baseline mechanisms and finding conventions.

## 2. New IISE Implementation

A new deterministic `ases_gate.py intent` subcommand evaluates an incoming instruction against the authorized Work Unit and produces a decision:

| Decision | Meaning | Exit |
|---|---|---|
| `ALLOW` | no violation detected; within existing authorization | 0 |
| `BLOCK` | prohibited action or explicit out-of-scope path | 1 |
| `REQUIRE_FOUNDER_APPROVAL` | governance change or out-of-scope objective | 2 |
| `REVIEW_REQUIRED` | no classifiable signal (ambiguous) | 2 |

Decision record: `ases-intent-decision/1` JSON with `instruction_source`, `work_unit_id`, `project_objective`, `decision`, `reasons`.

## 3. Project-Level Objective Protection

`OUT_OF_SCOPE_OBJECTIVES` patterns (Universal-Orchestrator, Harness², USHE) → `REQUIRE_FOUNDER_APPROVAL`. An objective is never made authoritative by an instruction; only the governance records define it.

## 4. Work Unit-Level Intent Protection

`PROHIBITED_ACTIONS` (commit, push/force-push, pr-create, credential/passphrase/access-token/`ghp_`/`github_pat_`, real-GitHub/production, UNKNOWN retry) → `BLOCK`. Explicit out-of-scope full paths (matched against `Files/modules allowed` via `fnmatch`) → `BLOCK`. Bare filenames are treated as ambiguous (skipped), avoiding false positives.

## 5. Instruction Authority Validation

`--source` labels the instruction origin (`founder`/`agent`/`tool-output`/`repository-doc`). The checker does **not** grant authorization from the source label — authorization remains in the governance records; the label is recorded for traceability only.

## 6. Conflict & Prompt-Injection Handling

`GOVERNANCE_CHANGES` (CONSTITUTION, APPROVED_DECISIONS, CURRENT_TASK, PROJECT_CONTEXT) → `REQUIRE_FOUNDER_APPROVAL`. Untrusted content (tool output, repository docs, agent-generated text) is treated as data: it can trigger BLOCK/REQUIRE_FOUNDER_APPROVAL but never ALLOW a change by itself.

## 7. Enforcement Level Achieved

- **Script-invoked deterministic check** (the `intent` subcommand), executed before authorization.
- **NOT** an execution-boundary interceptor: the checker cannot technically prevent an Agent from bypassing it; it is a supervised check that must be invoked in the workflow.
- **Post-execution** delta/scope enforcement remains the authoritative detection for actual file changes.

## 8. Tests Executed & Results

`tests.test_ases_gate.IntentChecks` (7 tests):

| Scenario | Result |
|---|---|
| Legitimate in-scope (founder) | **EXECUTED PASS** → ALLOW |
| Out-of-scope objective | **EXECUTED PASS** → REQUIRE_FOUNDER_APPROVAL |
| Out-of-scope path | **EXECUTED PASS** → BLOCK |
| Commit/push | **EXECUTED PASS** → BLOCK |
| Governance change (Constitution) | **EXECUTED PASS** → REQUIRE_FOUNDER_APPROVAL |
| Credential access (tool-output) | **EXECUTED PASS** → BLOCK |
| Ambiguous | **EXECUTED PASS** → REVIEW_REQUIRED |

Full suite: **179 tests OK (skipped=1)**.

## 9. False-Positive / False-Negative Measurements

On the 7 executed scenarios: **0 false positives** (legitimate in-scope instruction → ALLOW), **0 false negatives** (every prohibited/out-of-scope/governance-change/credential scenario correctly non-ALLOW). This is a small deterministic test set; it is **not** claimed as general semantic drift detection.

## 10. Performance Overhead

`intent` is a pure regex/fnmatch check over a short text plus one governance-record read — negligible (the 7-test run completed in ~2.3 s). No semantic LLM call.

## 11. Remaining Limitations

- **Deterministic only:** semantic/indirect objective drift that does not match the explicit patterns is not detected.
- **Not an interceptor:** pre-execution blocking relies on the check being invoked; an Agent can technically bypass it (disclosed, not claimed otherwise).
- **Bare-filename scope ambiguity:** bare filenames are not deterministically scoped (skipped).
- Interactive/prompt-injection scenarios that require a real console remain Founder-dependent.

## 12. Compatibility

Adds a new `intent` subcommand; no change to existing `check`/`baseline`/policy/manifest behavior. Existing adapters (`ases-agent`) and the DSH integration are unaffected; no new dependency; no architecture change.

---

**Not declared:** formal Phase 1 acceptance. IISE is a subsequent Core enhancement; Founder retains final authority over architecture and acceptance.
