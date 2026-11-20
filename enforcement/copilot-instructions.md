# ASES Mandatory Instructions

Before working, read the complete ASES `CONSTITUTION.md` (in an adopted project: `docs/governance/ases/CONSTITUTION.md`, or the `snapshot_dir` recorded in `docs/governance/ases.lock.json`), the target project's `docs/governance/PROJECT_CONTEXT.md`, approved decisions, scope, constraints, current milestone and `docs/governance/CURRENT_TASK.md`.

In an adopted project, run `python docs/governance/ases/scripts/ases_gate.py check --project-root . --task docs/governance/CURRENT_TASK.md`. If the gate blocks, or required governance documents are missing or inaccessible, stop before implementation and report the blocker.

Follow the Constitution. Do not expand scope or alter approved decisions without explicit Founder approval. Do not claim tests passed without execution and evidence. Do not self-approve milestones, task scope or Founder acceptance. Do not officially integrate work before Founder acceptance. Protect secrets, user/runtime data and Git history; never force-push.

Report changed files, commands and tests executed, results, evidence, known issues, deviations and Git status.
