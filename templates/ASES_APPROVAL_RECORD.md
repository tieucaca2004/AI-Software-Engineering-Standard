---
record_schema: ases-approval/1
from_version: <none for first adoption, otherwise the currently adopted ASES version>
to_version: <ASES version being adopted>
to_manifest_sha256: <manifest sha256 printed in the lock for the adopted snapshot>
change_request: <Change Request ID from templates/CHANGE_REQUEST.md, or "none" for first adoption>
diff_reviewed: <yes after reviewing `ases_verify.py diff`, or not-applicable for first adoption>
founder_decision: <Approved | Rejected | Deferred>
founder_approval_date: <YYYY-MM-DD>
evidence: <where the Founder's explicit decision can be inspected: PR/issue/message link or document reference>
---

# ASES VERSION TRANSITION APPROVAL RECORD

Project:
Repository:

## Transition
- From ASES version:
- To ASES version:
- Reason for the transition:

## Review performed
- `ases_verify.py diff` output reviewed by:
- Summary of impact on this project (see Change Request):
- Constitution changed in this transition: Yes / No

## Founder decision
- Decision: Approved / Rejected / Deferred
- Founder name:
- Date:
- Conditions, if any:

## Rules
- Fill the front-matter fields (between the `---` lines) only after the Founder has explicitly decided.
  Template placeholders (`<...>`) make `ases_verify.py verify` fail on purpose.
- A first adoption uses `from_version: none` and `change_request: none`. An upgrade or rollback
  must reference a Change Request and use `diff_reviewed: yes`; `from_version` and `to_version`
  must differ.
- `evidence` must identify where the explicit decision can be inspected. `self`, `agent`, `none`,
  `implied` and `silence` are rejected.
- A lock file, a Git commit, a passing verification or silence is NOT approval (Constitution, Articles 12 and 31).
- This record is project-owned and self-declared. `ases_verify.py` checks that it exists, is well formed and
  matches the lock; it cannot prove the decision was made. Protect it with the project's review process.
- A rollback to an earlier ASES version is a new transition and needs its own record.
