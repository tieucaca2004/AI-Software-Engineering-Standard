# ASES — Mandatory Claude Code Instructions

@CONSTITUTION.md

Before every task:
- Read the complete Constitution above (not only this summary).
- Read the project's approved decisions, scope, constraints, current milestone and task authorization.
- In an adopted project, read `docs/governance/PROJECT_CONTEXT.md` and `docs/governance/CURRENT_TASK.md`, then run `python docs/governance/ases/scripts/ases_gate.py check --project-root . --task docs/governance/CURRENT_TASK.md`; stop if it blocks.
- Inspect Git status and the relevant code before editing.
- Confirm the authorized scope and acceptance criteria.
- If the Constitution, Project Context or required task authorization cannot be read, stop before implementation and report the blocker.

Never change approved architecture, locked decisions, scope, production data, dependencies or unrelated modules without explicit Founder approval. Never claim tests passed without running them. Never self-approve a milestone, task scope or Founder acceptance. Preserve secrets, user/runtime data and remote Git history.

At the end, report exact files changed, commands executed, test results, evidence, remaining risks and Git status. Wait for explicit Founder acceptance before official integration.
