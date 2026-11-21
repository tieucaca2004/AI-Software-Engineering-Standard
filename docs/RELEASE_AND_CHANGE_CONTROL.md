# ASES Release and Change Control

1. The root `CONSTITUTION.md` is the canonical policy. ASES Constitution 1.0 is unchanged by the 1.1.0 tooling release.
2. Changes require a documented proposal, impact analysis and explicit Founder approval.
3. Update `VERSION` and `CHANGELOG.md` together.
4. Review all tool adapters for consistency with the canonical Constitution, Project Context and current-task requirements.
5. Run local policy checks, the manifest check, the UAM tests and the governance gate tests.
6. Create a reviewed pull request.
7. Merge only after required human approval and required checks pass.
8. Tag the approved release.
9. Project repositories update their pinned Constitution snapshots through their own approved change process.

A change to the standard does not automatically change any project's approved architecture, scope or locked decisions. A passing check, a lock or a commit is not Founder acceptance.
