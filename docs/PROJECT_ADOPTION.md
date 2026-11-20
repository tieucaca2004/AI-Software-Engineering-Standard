# Project Adoption Procedure

This is the single authoritative procedure for adopting ASES in a project, without retroactively
changing its approved architecture or scope. Formats, checks and limits are specified in
`docs/UAM.md`. Every step is performed by a person; no tool installs, copies or updates anything.

## Authoritative locations

| Item | Location | Owner |
|---|---|---|
| **The Constitution (only authoritative copy)** | `<snapshot_dir>/CONSTITUTION.md`, default `docs/governance/ases/CONSTITUTION.md` | ASES-managed, verified by `ases_verify.py` |
| Snapshot directory path | `snapshot_dir` field of `docs/governance/ases.lock.json` | project (declared; the tool resolves everything from it) |
| Lock and approval records | `docs/governance/ases.lock.json`, `docs/governance/ases-approvals/` | project |
| Project Context / Specification | `docs/governance/PROJECT_CONTEXT.md` | project, completed before implementation |
| Current task authorization | `docs/governance/CURRENT_TASK.md` | project, created or approved by the Founder/authorized lead |
| Approved decisions, compliance profile, milestone records | `docs/governance/` | project |
| AI instruction files | project root, `.cursor/`, `.github/` | project |
| CI governance check | `.github/workflows/ases-governance.yml` | project, from `templates/ases-governance.yml` |

There must be **no second copy** of the Constitution (for example
`docs/governance/CONSTITUTION.md`, which earlier instructions suggested). Such a copy is
unverified and can silently diverge. If a project has one, do not keep it in parallel: replace it
with a pointer to the snapshot path through a reviewed change, and record that decision in
`docs/governance/APPROVED_DECISIONS.md`.

## 1. Before adoption

- Identify repository, primary branch and current working tree (it must be clean).
- Read the project's existing approved decisions, constraints and instruction files.
- Record the current milestone and release state.
- Identify secrets, runtime data, generated files and local configuration that must not be committed.
- Do not refactor or modify application code as part of policy installation unless separately approved.
- The Founder explicitly approves adopting the specific ASES release (recorded in section 3).

## 2. Vendor the snapshot (pinned)

Use a local checkout of the approved ASES release (`$ASES`) and the target project (`$PROJECT`).

1. In `$ASES`: `python scripts/ases_verify.py manifest --check` must pass.
2. The snapshot directory must not exist yet. If it exists, stop: this is an upgrade (section 9),
   not an adoption.
3. Copy `ases-manifest.json` and every file listed in its `files` array into the snapshot directory,
   keeping relative paths. Copy nothing else.

   Bash / WSL:
   ```
   cd "$ASES"
   if [ -e "$PROJECT/docs/governance/ases" ]; then
     echo "already adopted: stop"
   else
     python -c "import json;print('\n'.join(['ases-manifest.json']+[f['path'] for f in json.load(open('ases-manifest.json'))['files']]))" | tr -d '\r' |
     while IFS= read -r f; do mkdir -p "$PROJECT/docs/governance/ases/$(dirname "$f")"; cp "$f" "$PROJECT/docs/governance/ases/$f"; done
   fi
   ```
   PowerShell:
   ```
   Set-Location $ASES
   if (Test-Path "$PROJECT\docs\governance\ases") { throw "already adopted" }
   $m = Get-Content ases-manifest.json -Raw | ConvertFrom-Json
   foreach ($f in @('ases-manifest.json') + $m.files.path) {
     $dest = Join-Path "$PROJECT\docs\governance\ases" $f
     New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
     Copy-Item $f $dest
   }
   ```
   CRLF/LF differences from Git settings do not matter: hashing normalizes them. The commands in
   this document are run from `$PROJECT` unless stated otherwise.

## 3. Record the Founder's decision and create the lock

The lock is generated only from a valid approval record, in this order:

1. Print the vendored manifest's hash (needed for the record):
   `python docs/governance/ases/scripts/ases_verify.py lock --project-root . --manifest-sha256`
2. **After** the Founder's explicit decision, create the record as a new file from
   `docs/governance/ases/templates/ASES_APPROVAL_RECORD.md`, for example
   `docs/governance/ases-approvals/adoption-<version>.md`, and fill every front-matter field
   (`from_version: none`). Do not overwrite an existing record.
3. Print and save the lock (use Git Bash/WSL/PowerShell 7 for `>`, see `docs/UAM.md` section 7):
   ```
   python docs/governance/ases/scripts/ases_verify.py lock --project-root . \
     --approval-record docs/governance/ases-approvals/adoption-<version>.md > docs/governance/ases.lock.json
   ```
   `lock` refuses (exit 1, nothing printed) unless the record exists, is well formed, says
   `Approved`, matches the snapshot version and manifest hash, and the snapshot itself verifies.
   If it refuses, your shell may have left an empty lock file: delete it, fix the problem, retry.
   Optional: `--source-commit <40-hex ASES commit>` records the declared source commit.
4. Run `python docs/governance/ases/scripts/ases_verify.py verify --project-root .` (offline,
   exit 0 required).

A lock, a commit or a passing `verify` is not approval. The record is self-declared evidence; the
real gate is the project's protected branch and Founder review of the adoption diff.

## 4. Connect AI tools (project-owned files are never overwritten)

The snapshot files are ASES-managed. The files below are **project-owned**. Check each target first.

- **Target does not exist:** create it. **Target exists:** do not copy, replace or regenerate it.
  Add the pointer by hand, then review the diff: it must contain additions only, and every existing
  rule and approved decision must remain. Commit only after that review (PR with Founder review).
  If instructions conflict, stop and report it (Constitution, Article 3).

| Tool | Target | Content for a new file | Content added to an existing file |
|---|---|---|---|
| Claude Code | `CLAUDE.md` | `@docs/governance/ases/CLAUDE.md` | the same line |
| Codex / `AGENTS.md` agents | `AGENTS.md` | `Follow docs/governance/ases/AGENTS.md and read docs/governance/ases/CONSTITUTION.md in full before any task.` | the same sentence |
| Cursor | `.cursor/rules/ases.mdc` | the content of `docs/governance/ases/enforcement/cursor/ases.mdc` | other rules stay untouched; if `ases.mdc` exists, merge by hand |
| GitHub Copilot | `.github/copilot-instructions.md` | the content of `docs/governance/ases/enforcement/copilot-instructions.md` | append that text by hand |
| Other agents | the tool's instruction file | adapt `docs/governance/ases/enforcement/generic/PROJECT_AI_INSTRUCTIONS.md` | merge by hand |

Guarded commands (bash; they create a file only when it is absent, otherwise they tell you to merge
by hand):
```
[ -e CLAUDE.md ] && echo "CLAUDE.md exists: add the pointer by hand" || printf '@docs/governance/ases/CLAUDE.md\n' > CLAUDE.md
[ -e .cursor/rules/ases.mdc ] && echo "ases.mdc exists: merge by hand" || { mkdir -p .cursor/rules && cp docs/governance/ases/enforcement/cursor/ases.mdc .cursor/rules/ases.mdc; }
git diff --numstat -- CLAUDE.md AGENTS.md .github/copilot-instructions.md   # 2nd column (deleted lines) must be 0
```
PowerShell equivalent:
`if (Test-Path .cursor\rules\ases.mdc) { 'exists: merge by hand' } else { New-Item -ItemType Directory -Force .cursor\rules | Out-Null; Copy-Item docs\governance\ases\enforcement\cursor\ases.mdc .cursor\rules\ases.mdc }`
(`Copy-Item` overwrites silently, so always keep the `Test-Path` guard.)

If `snapshot_dir` is not the default, adjust the paths. Paths written inside snapshot files are
relative to the snapshot directory. Claude Code resolves `@` imports relative to the importing file,
but verify this for your version (section 7). Copies placed outside the snapshot are project-owned,
unverified, and can drift from it. Instructions improve compliance; they do not enforce it or prove it.

## 5. Complete the Project Context and current task

Before implementation starts, create these project-owned records from the snapshot templates:

1. `docs/governance/PROJECT_CONTEXT.md` from `templates/PROJECT_CONTEXT.md`.
   - Fill every section: identity, business problem/users, scope in/out, requirements with
     acceptance criteria and status, architecture/data, security/quality, delivery plan, current
     milestone and Founder decisions.
   - Replace every `<...>` placeholder. At least one Functional and one Non-functional requirement
     must be present, and at least one requirement must be `Specified` or `Approved`.
2. `docs/governance/CURRENT_TASK.md` from `templates/CURRENT_TASK.md`.
   - The Founder or an explicitly authorized lead fills and authorizes it. The coding agent must
     not create or widen its own task authorization.
   - `Status` must be exactly `Authorized`. List allowed files/modules, prohibited actions, testing
     requirements, acceptance criteria and the authorization evidence reference.
3. `docs/governance/APPROVED_DECISIONS.md` from `templates/APPROVED_DECISIONS.md`.
4. `docs/governance/PROJECT_COMPLIANCE_PROFILE.md` from `templates/PROJECT_COMPLIANCE_PROFILE.md`.

Governance records must be populated from verified project records. Do not invent decisions or infer
approval.

## 6. Install the CI governance check

Copy `docs/governance/ases/templates/ases-governance.yml` to
`.github/workflows/ases-governance.yml`. It runs:

```
python docs/governance/ases/scripts/ases_verify.py verify --project-root .
python docs/governance/ases/scripts/ases_gate.py check --project-root . --task docs/governance/CURRENT_TASK.md
```

Configure the `ASES governance gate` job as a required status check in the protected-branch ruleset.
If the project uses a non-default `snapshot_dir`, adjust the workflow paths. Do not weaken the
workflow to make a failing gate pass.

## 7. Validate

- Run the gate:
  `python docs/governance/ases/scripts/ases_gate.py check --project-root . --task docs/governance/CURRENT_TASK.md`
  (offline; exit 0 required).
- Run the snapshot verifier: `python docs/governance/ases/scripts/ases_verify.py verify --project-root .`.
- Confirm each AI tool loads the expected instruction file.
- Start a new session and ask the agent to identify the Constitution version, Project Context,
  current authorized task and locked decisions, with file references.
- Confirm the agent stops if a required document is unavailable or the gate blocks.
- Enable the CI governance check and configure branch protection/required reviews, including
  `docs/governance/**`.

The ASES repository's own `scripts/ases_preflight.py` checks the ASES repository root, not an
adopted project.

## 8. Approval

Submit the adoption diff, the approval record, the Project Context and the governance records to
the Founder. Adoption is not complete until explicitly approved. A passing gate, a lock or a green
CI run is not Founder approval.

## 9. Updating ASES (or rolling back)

Never automatic. For a new or older ASES release:
1. Obtain it locally and run
   `ases_verify.py diff --project-root . --proposed <dir>` to review every change (it also prints
   the proposed manifest hash needed for the record).
2. Review the changelog, analyze project impact, and prepare a Change Request
   (`templates/CHANGE_REQUEST.md`).
3. Obtain explicit Founder approval and record it in a **new** record from
   `templates/ASES_APPROVAL_RECORD.md`.
4. Only then replace the snapshot to match the new manifest's file set, generate the new lock as in
   section 3 (it refuses without the matching approved record), and update instruction references.
5. Re-run the gate, `verify`, the compliance checks and the CI workflow; commit through the normal
   review process.

## 10. Operating rules

- A task record is not a substitute for Founder approval of a milestone.
- Do not merge an unaccepted milestone; do not self-approve a task, PR or release.
- Do not bypass a failing gate, protected branch, required review or CI check.
- Never force-push or rewrite remote history.
- Protect secrets, user data, runtime data and Git history.
