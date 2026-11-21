# ASES — Mandatory Repository Governance

Before any task that reads, writes, executes, tests, commits, or changes this repository:

1. Read the complete authoritative Constitution in full: `CONSTITUTION.md` in the ASES source repository, or `<snapshot_dir>/CONSTITUTION.md` (default `docs/governance/ases/CONSTITUTION.md`) in an adopted project.
2. Read `docs/PROJECT_ADOPTION.md`, `docs/ENFORCEMENT_MODEL.md` and `docs/LIFECYCLE_GATES.md` as relevant.
3. If this repository is an adopted ASES project, read `docs/governance/PROJECT_CONTEXT.md`,
   `docs/governance/APPROVED_DECISIONS.md`, the current scope/milestone records and
   `docs/governance/CURRENT_TASK.md`. Run
   `python docs/governance/ases/scripts/ases_gate.py check --project-root . --task docs/governance/CURRENT_TASK.md`
   and stop if it blocks.
4. In the ASES source repository, read the Founder-authorized task scope and the applicable
   decision records; do not infer authorization from a branch, commit or silence.
5. Inspect the working tree and identify the authorized task scope.
6. State any conflict, missing authority, unavailable policy file or unclear acceptance criterion before implementation.

Mandatory:
- Follow the Constitution and project-specific approved decisions.
- Project-specific decisions approved by the Founder take precedence over the general ASES standard where they conflict, as defined in the Constitution.
- Do not expand scope or alter locked decisions without explicit approval.
- Do not implement in an adopted project without a complete Project Context and an `Authorized` current-task record.
- Do not claim tests, security checks, persistence, integration or deployment succeeded unless actually executed and evidenced.
- Do not self-approve a milestone, task scope or Founder acceptance.
- Do not officially integrate an unaccepted milestone.
- Protect secrets, user data, runtime data and Git history.
- Never force-push.
- Stop affected work if required policy or approval is unavailable.

At completion, provide a Milestone Completion Report with changed files, tests and results, evidence, known issues, security review, Git status and deviations.
