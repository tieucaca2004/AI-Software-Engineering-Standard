# ASES Universal Adoption Mechanism (UAM): MVP Reference

UAM lets any repository adopt a **pinned, vendored snapshot** of ASES, then verify it **offline**.
Procedure: `docs/PROJECT_ADOPTION.md`. This file is the reference for formats, checks and limits.

## 1. Model and data flow

```
 ASES repo (source of truth)                     Project repo (independent after adoption)
 ┌──────────────────────────┐   manual copy      ┌──────────────────────────────────────────┐
 │ CONSTITUTION.md ...      │ ─────────────────► │ docs/governance/ases/   ASES-managed     │
 │ ases-manifest.json       │  (a person, after  │   (snapshot + ases-manifest.json)        │
 │ scripts/ases_verify.py   │   Founder approval)│ docs/governance/ases.lock.json  declared │
 └──────────────────────────┘                    │ docs/governance/ases-approvals/*.md      │
        nothing flows back                       │ PROJECT_CONTEXT.md, CURRENT_TASK.md ...  │
                                                 │ AGENTS.md, CLAUDE.md, .cursor/...  yours │
                                                 └──────────────────────────────────────────┘
```

There is no installer, updater, network call or telemetry. Every change to a project is made by a person.

### 1.1 Five components only

The approved UAM MVP has exactly five components:

1. **Constitution Snapshot** — the vendored, manifest-covered ASES files.
2. **AI Adapters** — project-owned instruction files that point at the snapshot and require the
   Project Context and current task.
3. **Version Lock** — `docs/governance/ases.lock.json`, pinning the snapshot manifest hash.
4. **Integrity Verify** — offline SHA-256 verification of the snapshot, lock and approval record.
5. **Founder Approval** — an explicit, self-declared approval record, enforced by review.

`scripts/ases_gate.py` and the Project Context are ASES **core governance controls**, not a sixth
UAM component. The gate consumes the UAM checks; it does not install, update, orchestrate or
monitor anything.

## 2. ASES-managed vs project-owned

| Kind | Where | Who may change it | Checked by `verify` |
|---|---|---|---|
| **ASES-managed** | everything under `snapshot_dir` (default `docs/governance/ases/`) | nobody in the project; replaced only through the approval process | yes: every file, plus unexpected files/directories |
| **Project-owned, ASES metadata** | `docs/governance/ases.lock.json`, approval records | the project, with Founder review | structure and consistency only |
| **Project-owned, governance** | `PROJECT_CONTEXT.md`, `CURRENT_TASK.md`, `APPROVED_DECISIONS.md`, `PROJECT_COMPLIANCE_PROFILE.md`, milestone records | the project, with Founder review | no (checked by `ases_gate.py`, not `verify`) |
| **Project-owned, instructions** | `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*`, `.github/copilot-instructions.md`, any other project rule file | the project | **no** (never read, never modified) |

Existing project-owned instruction files are never replaced. Integration is by adding a pointer (see
`docs/PROJECT_ADOPTION.md`, section 4). The only authoritative Constitution in a project is
`<snapshot_dir>/CONSTITUTION.md`; a second copy elsewhere is not supported.

## 3. The snapshot

The managed set is fixed and listed in `ases-manifest.json` (field `files`):
`CONSTITUTION.md`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `CLAUDE.md`,
`docs/ENFORCEMENT_MODEL.md`, `docs/LIFECYCLE_GATES.md`, `docs/PROJECT_ADOPTION.md`,
`docs/RELEASE_AND_CHANGE_CONTROL.md`, `docs/UAM.md`,
`enforcement/copilot-instructions.md`, `enforcement/cursor/ases.mdc`,
`enforcement/generic/PROJECT_AI_INSTRUCTIONS.md`, `scripts/ases_gate.py`,
`scripts/ases_verify.py`, `templates/APPROVED_DECISIONS.md`,
`templates/ASES_APPROVAL_RECORD.md`, `templates/CHANGE_REQUEST.md`, `templates/CURRENT_TASK.md`,
`templates/MILESTONE_COMPLETION_REPORT.md`, `templates/PROJECT_COMPLIANCE_PROFILE.md`,
`templates/PROJECT_CONTEXT.md`, `templates/ases-governance.yml`. Relative paths are preserved
inside `snapshot_dir`, so relative references (such as `@CONSTITUTION.md` inside the snapshot's
`CLAUDE.md`) keep working. `ases-manifest.json` is copied next to them but is not listed in itself.

Manifest format (`ases-manifest/1`, JSON, keys in this order, files sorted by path):

```json
{ "schema": "ases-manifest/1", "ases_version": "1.1.0", "canonicalization": "text-lf-v1",
  "hash_algorithm": "sha256", "files": [ { "path": "CONSTITUTION.md", "sha256": "<64 hex>" } ] }
```

Invalid or ambiguous manifests are rejected: duplicate or unknown keys, unsorted or duplicate paths
(case-insensitive), unsafe paths, missing `CONSTITUTION.md`/`VERSION`, wrong schema, non-hex hashes.

### Canonicalization `text-lf-v1`

A file's hash is SHA-256 of its bytes after: (1) rejecting a UTF-8 BOM, NUL bytes and invalid UTF-8;
(2) replacing every `CRLF` with `LF`; (3) rejecting any remaining lone `CR`. Nothing else is normalized.
LF and CRLF checkouts (Windows `autocrlf`, WSL) therefore hash identically, while BOMs, UTF-16 and
mixed/lone-CR endings fail instead of being silently accepted. Plain `sha256sum` / `Get-FileHash`
hash raw bytes and match only for LF files; use `ases_verify.py` for the authoritative result.

## 4. Version lock (`docs/governance/ases.lock.json`, schema `ases-lock/1`)

```json
{ "schema": "ases-lock/1", "ases_version": "1.1.0", "snapshot_dir": "docs/governance/ases",
  "manifest": { "sha256": "<canonical sha256 of snapshot_dir/ases-manifest.json>" },
  "source": { "repository": "https://github.com/...", "commit": null },
  "approval": { "record": "docs/governance/ases-approvals/adoption-1.1.0.md" } }
```

Exact key set, deterministic key order and layout (`ases_verify.py lock` prints it). Unknown or
duplicate keys are errors.

| Field | Status |
|---|---|
| `ases_version` | **Verified**: must equal the manifest's version and the snapshot's `VERSION` file |
| `manifest.sha256` | **Verified**: recomputed from the vendored manifest |
| `snapshot_dir` | Verified to be a safe project-relative path that exists |
| `source.repository`, `source.commit` | **Declared**, not verifiable offline (`commit` may be `null`) |
| `approval.record` | **Declared**: existence and consistency are checked, the decision is not provable |

A lock file is **not** proof of Founder approval.

## 5. Verification and the task-entry gate

```
python docs/governance/ases/scripts/ases_verify.py verify --project-root .
python docs/governance/ases/scripts/ases_verify.py verify --project-root . --expect-version 1.1.0
```

Standard library only; no network, no file writes (no subcommand writes any file); it refuses to
follow links and unsafe paths. Checks: lock structure; manifest structure and hash; version
agreement; every managed file's SHA-256; unexpected files, links and empty directories in the
snapshot; approval-record presence, structure and agreement with the lock. `lock` itself verifies
the snapshot before printing a lock, so it cannot bless tampered files.

| Finding | Meaning |
|---|---|
| `LOCK_MISSING` / `LOCK_INVALID` | no lock, or malformed/ambiguous lock |
| `MANIFEST_INVALID` / `MANIFEST_MISMATCH` | malformed manifest, or not the one the lock pins |
| `VERSION_MISMATCH` | lock, manifest, `VERSION` file or `--expect-version` disagree |
| `FILE_MISSING` / `FILE_MODIFIED` / `FILE_UNEXPECTED` / `FILE_INVALID` | managed-file problems (invalid = link or non-file) |
| `APPROVAL_RECORD_INVALID` | record missing, malformed, not `Approved`, or not matching the lock |

Exit codes: `0` pass, `1` verification failed, `2` usage error or unexpected error (integrity not
established). Any non-zero code must be treated as failure. Nothing is repaired automatically.

Before implementation, an adopted project also runs the core governance gate:

```
python docs/governance/ases/scripts/ases_gate.py check \
  --project-root . --task docs/governance/CURRENT_TASK.md
```

It verifies the snapshot/lock/approval (when adopted), the required Project Context sections and
fields, and the `Authorized` current-task record. It is offline and read-only. Exit `0` allows
implementation; `1` blocks; `2` means the check could not run.

Other read-only subcommands: `lock` (prints a lock for a vendored snapshot; it **refuses** unless the
referenced approval record exists, is well formed, says `Approved`, matches the snapshot version and
manifest hash, and the snapshot verifies; `lock --manifest-sha256` prints just the manifest hash
needed to fill the record), `manifest [--check]` (ASES source side), `diff --proposed DIR`
(section 6; it refuses a proposed release whose `VERSION` file disagrees with its manifest).

## 6. Founder approval of a version change

1. Obtain the proposed ASES release as a local directory (for example a checkout of the release tag).
2. `python docs/governance/ases/scripts/ases_verify.py diff --project-root . --proposed <dir>` shows
   added, removed and changed files with text diffs. It refuses if the installed snapshot or the
   proposed release does not verify.
3. The Founder reviews the diff and the changelog, and decides (Change Request per
   `templates/CHANGE_REQUEST.md`).
4. Only after an explicit Founder decision, fill `templates/ASES_APPROVAL_RECORD.md` into the project
   as a new record (evidence field = where the decision can be inspected; `to_manifest_sha256` = the
   proposed manifest hash printed by `diff`). A first adoption uses `from_version: none` and
   `change_request: none`; an upgrade or rollback must reference a Change Request. `evidence` must
   name an inspectable decision; `self`, `agent`, `none`, `implied` and `silence` are rejected.
5. A person then replaces the snapshot, prints a new lock with `lock` (it refuses without the matching
   approved record), saves it, and runs `verify` and the gate.
6. Rollback to an older version is a new transition with its own record.

Nothing infers approval from a lock, a commit, a green `verify`, a passing gate or silence. `verify`
cannot check that step 3 happened before step 5; real enforcement is the project's protected branch
and required review of `docs/governance/**`.

## 7. Maintainer release procedure (ASES repository)

Any change to a managed file requires `python scripts/ases_verify.py manifest > ases-manifest.json`,
then `python scripts/ases_verify.py manifest --check` (also run in CI). Update `VERSION` and
`CHANGELOG.md` together under the existing Release and Change Control rules
(`docs/RELEASE_AND_CHANGE_CONTROL.md`). The current candidate is ASES 1.1.0; the Constitution remains
ASES Constitution 1.0. In Windows PowerShell 5.1 `>` writes UTF-16; use PowerShell 7, Git Bash or
WSL, or `| Out-File -Encoding ascii` (the tool rejects BOMs and UTF-16).

## 8. Limitations and security boundaries

- Hashes detect change, not forgery: no signatures exist. Anyone able to rewrite the snapshot,
  manifest, lock and tool together can make `verify` pass. Use protected branches, `CODEOWNERS` and
  Founder review.
- The vendored `ases_verify.py` is itself covered by the manifest, but a modified copy can lie about
  itself.
- Instruction files (`CLAUDE.md`, `AGENTS.md`, Cursor, Copilot) are guidance. They do not prove or
  enforce agent compliance or security. Technical controls remain permissions, CI, branch protection
  and human review.
- The gate checks document completeness and task authorization, not whether a model read or obeyed
  anything, and not whether an approval record is genuine.
- Instruction files outside the snapshot (including copies placed at `.cursor/rules/ases.mdc` or
  `.github/copilot-instructions.md`) are project-owned and unverified; they can drift from the snapshot.
- Tested on Python 3.13 (Windows); the code targets Python 3.12+ and uses only the standard library.
  Symbolic links are rejected on every version; Windows junction detection relies on
  `os.path.isjunction` (Python 3.12+). Junction rejection is covered by a Windows-only test.
  Symlink creation was not permitted in the local test environment; the symlink test is skipped there.
- Tool loading behaviour (imports, rule discovery) can change; validate it as in
  `docs/PROJECT_ADOPTION.md` section 7.
- Not provided: installer/`apply`, automatic updates or watchers, signatures or key management, fleet
  management, telemetry. No project data ever goes back to ASES.
