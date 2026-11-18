# Project Adoption Procedure

This procedure applies ASES to a project without retroactively changing its approved architecture or scope.

## 1. Before adoption
- Identify repository, primary branch and current working tree.
- Read the project's existing approved decisions and constraints.
- Record the current milestone and release state.
- Identify secrets, runtime data, generated files and local configuration that must not be committed.
- Do not refactor or modify application code as part of policy installation unless separately approved.

## 2. Install the canonical Constitution
Recommended initial adoption: copy the released `CONSTITUTION.md` into `docs/governance/CONSTITUTION.md` in the project. Record the ASES version and source repository/release in the Project Compliance Profile.

A project-local copy is a pinned snapshot. Updates must be intentional and reviewed; do not silently replace it.

## 3. Install the correct AI instructions
- Copy `AGENTS.md` to the project root for compatible agents.
- Copy `CLAUDE.md` to the project root for Claude Code.
- Copy `enforcement/cursor/ases.mdc` to `.cursor/rules/ases.mdc`.
- Copy `enforcement/copilot-instructions.md` to `.github/copilot-instructions.md`.

Ensure instructions point to the actual project-local Constitution path. For example, replace `@CONSTITUTION.md` in a project-level Claude file with `@docs/governance/CONSTITUTION.md`.

Do not overwrite existing instruction files. Merge carefully and preserve existing approved project-specific rules. Review the resulting diff.

## 4. Add governance records
Create or update:
- `docs/governance/APPROVED_DECISIONS.md`
- `docs/governance/PROJECT_COMPLIANCE_PROFILE.md`
- Current scope and milestone documents.

Populate them from verified project records. Do not invent decisions or infer approval.

## 5. Validate
- Run the ASES preflight.
- Confirm each AI tool loads the expected instruction file.
- Start a new session and ask the agent to identify the Constitution version, project scope and locked decisions, with file references.
- Confirm the agent stops if a required document is unavailable.
- Enable CI policy checks.
- Configure branch protection and required reviews.

## 6. Approval
Submit the adoption diff and compliance profile to the Founder. Adoption is not complete until explicitly approved.

## 7. Updating ASES
When a new ASES version is released:
- Review the changelog.
- Compare the old and new Constitution.
- Analyze project impact.
- Create a project-specific update proposal.
- Obtain Founder approval.
- Update the pinned copy and instruction references.
- Re-run compliance checks.
