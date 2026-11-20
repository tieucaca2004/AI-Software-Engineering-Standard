# ASES Lifecycle Gates G0–G7

This document makes the Constitution's lifecycle (Articles 13–14 and 31–32)
operational. It does not replace the Constitution and does not create a second
lifecycle. A gate is passed only when the listed evidence exists and has been
reviewed; a document that merely says a gate passed is not evidence.

## Gate summary

| Gate | Purpose | Minimum artifacts | Entry condition | Exit evidence |
|---|---|---|---|---|
| G0 Discovery | Define the real problem and product boundary | Problem statement, users, goals, in/out scope, constraints, assumptions, success measures | Authorized discovery task | Discovery record reviewed by the accountable owner; assumptions and open questions recorded |
| G1 Requirements | Turn the problem into testable requirements | SRS or equivalent, functional and non-functional requirements, business rules, acceptance criteria, error scenarios, data requirements, open questions | G0 evidence | Requirements reviewed against G0 |
| G2 Architecture | Define the technical structure before significant implementation | Context, components, data flow, data model, API/contract, auth design, error handling, logging/monitoring, deployment, backup/recovery, ADRs | G1 requirements stable enough to design | Architecture review; ADRs recorded |
| G3 Planning | Split work into verifiable milestones | Implementation plan, milestone/task breakdown, dependencies, risks, test plan, per-milestone Definition of Done | G2 architecture reviewed where applicable | Plan reviewed and current milestone authorized by the accountable owner |
| G4 Implementation | Implement only the authorized scope | Current task record, complete project context, diff, tests, evidence | G0–G3 evidence and an Authorized task | Implementation complete, tests executed, no unapproved deviation |
| G5 QA | Verify the implementation against requirements | Test report, commands, commit/build, environment, pass/fail/skipped counts, security and regression evidence, known defects | G4 implementation report | QA evidence reviewed; blockers declared |
| G6 Founder Acceptance | Founder decides | Milestone Completion Report, scope comparison, test/CI evidence, security status, Git status, risks, deviations | G5 evidence | Explicit Founder decision: Accepted, Accepted with Conditions, or Rejected |
| G7 Integration & Release | Integrate or release only after acceptance | Acceptance decision, release plan, rollback plan, protected-branch review, post-integration verification | G6 Accepted (conditions resolved) | Integration/release evidence and post-release verification |

## Non-negotiable gate rules

1. Do not start G4 without a complete Project Context and an `Authorized` task record.
2. Do not skip a gate because the project is small. Scale the artifacts, not the decision.
3. Do not mark G5 passed without executing the required tests. Skipped tests are not passed.
4. Do not mark G6 accepted without an explicit Founder decision. Silence, a green CI run or a commit is not acceptance.
5. Do not start G7 before G6 acceptance. Accepted with Conditions does not automatically authorize release.
6. Record every deviation and Change Request. Do not silently change architecture, data, dependencies or scope.
7. Preserve the Constitution, approved decisions, secrets, user data, runtime data and Git history.

## Minimum evidence per implementation task

- Project context path and version.
- Current task record with `Status: Authorized` and an authorization reference.
- Exact commands executed and their results.
- Test counts: passed, failed, skipped, not tested.
- Commit SHA and branch.
- Security review: secrets, permissions, data protection, dependencies.
- Known issues, limitations and deviations.
- Founder acceptance status. Development complete is not acceptance.

## Gate failure behavior

A failed gate blocks the affected workstream. Preserve the current state, report
the exact missing or invalid artifact, and do not implement around the gate. If a
gate cannot be evaluated because a required record, permission or decision is
unavailable, report it as BLOCKED rather than guessing.
