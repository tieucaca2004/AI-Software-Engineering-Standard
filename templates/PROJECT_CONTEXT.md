# PROJECT CONTEXT

> Complete this file from verified project records before implementation starts.
> Do not invent a requirement, approval or architecture decision. Replace every
> `<...>` placeholder. The ASES gate blocks placeholders, missing sections and
> incomplete requirements.

Project:
Context version:
Last updated:
Prepared by:
Approved by:
Approval evidence:

## 1. Project Identity

- Project name: <project name>
- Project ID: <stable project ID>
- Repository: <repository URL or path>
- Primary branch: <branch>
- Owner: <accountable owner>

## 2. Business Problem and Users

Describe the real problem, affected users, current process, pain points and the
business outcome expected. Do not start from a UI idea.

- Problem:
- Users / stakeholders:
- Current process and pain:
- Expected outcome:
- Success measures:

## 3. Scope

### In scope

- <specific capability or outcome>

### Out of scope

- <explicit exclusion>

## 4. Requirements

Every requirement must have an ID, a type, testable acceptance criteria and a
status. Use at least one Functional and one Non-functional requirement. Status
must be one of Proposed, Specified, Approved, Implemented, Tested, Verified,
Accepted or Deferred. At least one row must be Specified or Approved before the
gate allows implementation.

| ID | Type | Requirement | Acceptance criteria | Status |
|---|---|---|---|---|
| REQ-001 | Functional | <what the system must do> | <observable pass/fail condition> | Specified |
| REQ-002 | Non-functional | <quality, security, performance or reliability requirement> | <measurable condition> | Specified |

## 5. Architecture and Data

Describe the approved architecture at the level appropriate to the project.
Use `N/A (reason)` only when a field genuinely does not apply.

- Data storage:
- API/integration:
- Authentication/authorization:
- Error handling:
- Deployment:
- Backup/recovery:
- Architecture decisions / ADR references:
- Data lifecycle, migration and retention:

## 6. Security and Quality

- Secrets:
- Permissions:
- Input validation:
- Audit logging:
- Dependency and supply-chain risk:
- Test strategy summary:
- Known security limitations:

## 7. Delivery Plan

- Milestones:
- Test strategy:
- Risks:
- Dependencies:
- Rollback plan:
- Evidence required at each gate:

## 8. Current Milestone

- Milestone ID:
- Objective:
- Authorized scope:
- Acceptance criteria:
- Status: Planned
- Target date:
- Evidence location:

## 9. Founder Decisions

- Approved decisions: docs/governance/APPROVED_DECISIONS.md
- Locked constraints:
- Open proposals (not approved):
- Exceptions approved by the Founder:

Rules: a proposal is not approval; silence is not approval; a task record does
not grant scope beyond this context. Changes to approved decisions require a
Change Request and explicit Founder approval.
