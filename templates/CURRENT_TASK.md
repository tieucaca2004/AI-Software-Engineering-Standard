# CURRENT TASK

> This is the task-entry authorization record. It is created or approved by the
> Founder or an explicitly authorized lead, not by the coding agent for its own
> work. Replace every `<...>` placeholder. The ASES gate blocks missing fields,
> placeholders and any Status other than Authorized.

- Task ID: <task ID>
- Project: <must match Project ID or Project name in PROJECT_CONTEXT.md>
- Agent: <agent or engineer receiving the task>
- Requested by: <person requesting the work>
- Date: <YYYY-MM-DD>
- Status: Authorized
- Objective: <one concrete outcome>
- Authorized scope: <what may be changed or produced>
- Files/modules allowed: <comma-separated project-relative paths or globs, or "all" only for an explicitly repo-wide task>
- Prohibited actions: <what must not be changed or executed>
- Implementation requirements: <constraints, patterns and approved decisions to preserve>
- Testing requirements: <commands, test types and evidence required>
- Acceptance criteria: <observable pass/fail conditions>
- Approved decisions reference: <path and decision IDs, or "none">
- Authorization evidence: <PR/issue/message/document reference where the authorization can be inspected>

## Notes

- `Files/modules allowed` is enforced when CI supplies `--changed-files`. Each changed path must
  match one of the comma-separated patterns. `*` matches any characters, including `/`; use
  `src/**` or `src/*.py` deliberately. Use `all` only for an explicitly repo-wide task.
- Do not edit this record to widen your own scope.
- If the task conflicts with the project context or approved decisions, stop and report the conflict.
- A commit, a passing check or silence is not Founder acceptance.
