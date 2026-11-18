# Project Adoption Procedure

This procedure applies ASES to a project without retroactively changing its approved architecture or scope.
Formats, checks and limits are specified in `docs/UAM.md`. Every step below is performed by a person; no tool
installs or updates anything.

## 1. Before adoption
- Identify repository, primary branch and current working tree (it must be clean).
- Read the project's existing approved decisions and constraints.
- Record the current milestone and release state.
- Identify secrets, runtime data, generated files and local configuration that must not be committed.
- Do not refactor or modify application code as part of policy installation unless separately approved.
- Founder explicitly approves adopting the specific ASES release (see section 6).

## 2. Install the ASES snapshot (vendored, pinned)
Use a local checkout of the approved ASES release (`$ASES`) and the target project (`$PROJECT`).

1. In `$ASES`: `python scripts/ases_verify.py manifest --check` must pass (source is consistent).
2. The snapshot directory must not exist yet (default `docs/governance/ases/`). If it exists, stop: this is an
   upgrade (section 7), not an adoption.
3. Copy `ases-manifest.json` and every file listed in its `files` array into the snapshot directory, keeping
   relative paths. Copy nothing else.

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
   CRLF/LF differences from Git settings do not matter: hashing normalizes them.
4. Create the approval record from `templates/ASES_APPROVAL_RECORD.md` (project-owned, for example
   `docs/governance/ases-approvals/adoption-<version>.md`) **after** the Founder's explicit decision; first fill
   `to_manifest_sha256` from step 5.
5. Print and save the lock (deterministic; use Git Bash/WSL/PowerShell 7 for `>`, see `docs/UAM.md` section 7):
   ```
   python docs/governance/ases/scripts/ases_verify.py lock --project-root . \
     --approval-record docs/governance/ases-approvals/adoption-<version>.md > docs/governance/ases.lock.json
   ```
   Optionally add `--source-commit <40-hex ASES commit>` before `>` to record the declared source commit.
6. Run `python docs/governance/ases/scripts/ases_verify.py verify --project-root .` (see section 5).

## 3. Connect AI tools (project-owned files are never overwritten)
The snapshot files are ASES-managed. The files below are **project-owned**. Never replace an existing one;
add the pointer by hand and review the diff (it must contain no deleted lines). Preserve every existing project
rule and approved decision. If instructions conflict, stop and report it (Constitution, Article 3).

| Tool | No file yet | File already exists |
|---|---|---|
| Claude Code | create `CLAUDE.md` containing `@docs/governance/ases/CLAUDE.md` | add that line to the existing `CLAUDE.md` |
| Codex / `AGENTS.md` agents | create `AGENTS.md` with: `Follow docs/governance/ases/AGENTS.md and read docs/governance/ases/CONSTITUTION.md in full before any task.` | append that sentence |
| Cursor | copy `docs/governance/ases/enforcement/cursor/ases.mdc` to `.cursor/rules/ases.mdc` | other rules stay untouched; if `ases.mdc` already exists, merge by hand |
| GitHub Copilot | copy `docs/governance/ases/enforcement/copilot-instructions.md` to `.github/copilot-instructions.md` | append the text of that adapter manually |
| Other agents | adapt `docs/governance/ases/enforcement/generic/PROJECT_AI_INSTRUCTIONS.md` | merge into the project's own instructions |

If `snapshot_dir` is not the default, adjust the paths. Paths written inside snapshot files are relative to the
snapshot directory. Claude Code resolves `@` imports relative to the importing file, but verify this for your
version (section 5). Copies placed outside the snapshot (`.cursor/rules/ases.mdc`, Copilot file) are project-owned,
unverified, and can drift from the snapshot. Instructions improve compliance; they do not enforce it or prove it.

## 4. Add governance records
Create or update:
- `docs/governance/APPROVED_DECISIONS.md`
- `docs/governance/PROJECT_COMPLIANCE_PROFILE.md` (record the pinned ASES version and lock path)
- Current scope and milestone documents.

Populate them from verified project records. Do not invent decisions or infer approval.

## 5. Validate
- Run `python docs/governance/ases/scripts/ases_verify.py verify --project-root .` (offline; exit 0 required).
  The ASES repository's own `scripts/ases_preflight.py` checks the ASES repository root, not an adopted project.
- Confirm each AI tool loads the expected instruction file.
- Start a new session and ask the agent to identify the Constitution version, project scope and locked decisions, with file references.
- Confirm the agent stops if a required document is unavailable.
- Enable CI policy checks and run `verify` in CI.
- Configure branch protection and required reviews (protect `docs/governance/**`).

## 6. Approval
Submit the adoption diff, the approval record and the compliance profile to the Founder. Adoption is not
complete until explicitly approved. A lock file, a commit or a passing `verify` is not approval.

## 7. Updating ASES (or rolling back)
Never automatic. For a new or older ASES release:
1. Obtain it locally and run `ases_verify.py diff --project-root . --proposed <dir>` to review every change.
2. Review the changelog, analyze project impact, and prepare a Change Request (`templates/CHANGE_REQUEST.md`).
3. Obtain explicit Founder approval and record it with `templates/ASES_APPROVAL_RECORD.md` (new record).
4. Only then replace the snapshot (same file set), print a new lock, and update instruction references.
5. Re-run `verify` and the compliance checks; commit through the normal review process.
