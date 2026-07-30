# Engineering Capability Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `engineering` as an independently versioned APM capability pack containing the controlled Matt Pocock engineering workflow, the existing owned skills, and tested Claude Code/Codex adapters.

**Architecture:** Carvel vendir owns one destination leaf per imported skill and one Git lock. This preserves repository-owned sibling skills while producing one conventional `engineering/skills/` tree for APM and native agent adapters. A small Python qualification command stages the vendir result, applies integration patches, enforces inventory and ownership policy, writes extended provenance, runs package checks, and swaps the package only after success. GitHub Actions qualifies updates and package-scoped tags.

**Tech Stack:** mise, Carvel vendir 0.46.0, Microsoft APM 0.26.0, Python 3.14.6, uv 0.11.8, PyYAML 6.0.3, pytest 9.1.1, Ruff 0.16.0, Renovate 43.285.7 for the adoption probe, GitHub Actions, Claude Code, Codex.

## Global Constraints

- Scope is `agent-skills` Stage 1 only. Do not modify `project-templates` or `dotagents`.
- Pin Python 3.14.6, uv 0.11.8, APM 0.26.0, vendir 0.46.0, pytest 9.1.1, Ruff 0.16.0, and PyYAML 6.0.3. Commit `uv.lock` for transitive pins.
- `engineering/` is the package root. Root `apm.yml` remains this repository's private consumer manifest and must not leak into the package.
- Preserve the owned skills `audit-third-party-software`, `context-extractor`, and `operating-omnigent`.
- Import upstream setup directly at `skills/setup-engineering-workflow-for-apm`, then transform it through the ordered repository-owned patch series. Never create a local skill named `setup-matt-pocock-skills`.
- Vendir owns payload acquisition, path filtering, legal-file copying,
  resolved-SHA locking, and locked reproduction. Refresh-time inventory
  reconciliation added in Task 8 may use a temporary shallow, filtered Git
  checkout only to enumerate skill directory names at the candidate commit.
  Python must not copy payload files or implement a second include/exclude
  copier.
- Imported files are generated. Changes come from the package's vendir manifests, `engineering/patches/series`, or the upstream ref.
- The first import is based on `mattpocock/skills` commit `2ab958093e83e0ec752e6c1c5932da465bf23e0c`, observed on 2026-07-28.
- GitHub Issue creation requires a complete review batch and an approval immediately before the first external write. Resume uses deterministic issue markers and must not duplicate confirmed issues.
- Claude Code and Codex must discover the same portable skill payload with empty user configuration directories.
- `engineering-vX.Y.Z` is the only package tag form. Automation may open a draft PR; it may not merge, tag, publish, or enable automerge.
- Pin every GitHub Action to an immutable commit SHA when implementing the workflows.

---

## File Map

**Repository tooling**

- `mise.toml` — pinned tools and the public maintainer tasks `vendor-engineering`, `vendor-engineering-check`, `test-engineering-package`, `test-engineering-agents`, and `test`.
- `pyproject.toml`, `uv.lock` — qualification/test dependencies and Ruff/pytest configuration.
- `tools/capability_pack/cli.py` — CLI parsing and exit codes.
- `tools/capability_pack/model.py` — immutable policy, inventory, provenance, and result types.
- `tools/capability_pack/qualify.py` — staging, vendir invocation, refresh-time leaf-inventory reconciliation, patch series, drift checks, owned-path checks, and atomic package swap.
- `tools/capability_pack/provenance.py` — stable SHA-256 manifests and YAML serialization.
- `tools/capability_pack/summary.py` — deterministic draft-PR evidence and semantic-version proposal.

**Engineering package**

- `engineering/vendir.yml`, `engineering/vendir.lock.yml` — leaf-level engineering and `grilling` policies with one resolved source lock.
- `engineering/provenance.yml` — generated inventory, mappings, hashes, and applied-patch evidence.
- `engineering/patches/series` and `engineering/patches/mattpocock-skills/*.patch` — ordered APM/setup and GitHub Issues adaptations.
- `engineering/LICENSES/mattpocock-skills/LICENSE` — upstream redistribution license selected through vendir.
- `engineering/apm.yml`, `engineering/.claude-plugin/plugin.json` — APM and Claude adapters at version `0.2.0`.
- `engineering/skills/setup-engineering-workflow-for-apm/` — generated setup skill and templates produced from upstream setup plus repository patches.
- `engineering/README.md`, `engineering/CLAUDE.md`, `engineering/CHANGELOG.md` — package use, editing contract, and release notes.

**Tests and automation**

- `tests/adoption/` — vendir layout and Renovate behavior probes.
- `tests/capability_pack/` — local fixture-driven qualification tests.
- `tests/fixtures/upstreams/mattpocock-skills/` — synthetic upstream variants.
- `engineering/tests/` — package, APM virtual-subdirectory, setup, issue, and conformance tests.
- `.github/workflows/engineering-ci.yml` — deterministic PR checks.
- `.github/workflows/engineering-upstream-check.yml` — weekly draft update PR.
- `.github/workflows/engineering-tag-check.yml` — human-created package-tag qualification.

### Task 1: Prove the adopted-tool boundaries

**Files:**
- Create: `mise.toml`
- Create: `pyproject.toml`
- Create: `uv.lock`
- Modify: `.gitignore`
- Create: `tests/adoption/test_vendir_layout.py`
- Create: `tests/adoption/test_renovate_vendir.py`
- Create: `tests/fixtures/vendir-upstream/skills/engineering/alpha/SKILL.md`
- Create: `tests/fixtures/vendir-upstream/skills/engineering/alpha/scripts/run.sh`
- Create: `tests/fixtures/vendir-upstream/skills/engineering/beta/SKILL.md`
- Create: `tests/fixtures/vendir-upstream/skills/engineering/setup-matt-pocock-skills/SKILL.md`
- Create: `tests/fixtures/vendir-upstream/skills/productivity/grilling/SKILL.md`
- Create: `tests/fixtures/vendir-package/skills/audit-third-party-software/SKILL.md`
- Create: `tests/fixtures/vendir-package/vendir.yml`
- Create: `tests/fixtures/renovate/vendir.yml`
- Create: `tests/fixtures/renovate/vendir.lock.yml`

**Interfaces:**
- Produces: the command environment used by every later task: `mise exec -- uv run pytest`, `vendir`, and `apm`.
- Produces: one vendir run with leaf destinations for `alpha/`, a second engineering skill, the setup alias, and `grilling/`, while preserving owned sibling skills.
- Produces: the updater decision: use the scheduled workflow in Task 8 unless Renovate 43.285.7 demonstrates that it can run the full qualification command and commit its outputs.

- [ ] **Step 1: Add the pinned tool and Python project**

Create `mise.toml` with:

```toml
[tools]
python = "3.14.6"
uv = "0.11.8"
"ubi:microsoft/apm" = "0.26.0"
"ubi:carvel-dev/vendir" = "0.46.0"
"npm:renovate" = "43.285.7"

[tasks.vendor-engineering]
run = "uv run python -m tools.capability_pack.cli update engineering"

[tasks.vendor-engineering-check]
run = "uv run python -m tools.capability_pack.cli check engineering"

[tasks.test-engineering-package]
run = "uv run pytest -q engineering/tests/test_contract.py engineering/tests/test_consumer_e2e.py"

[tasks.test-engineering-agents]
run = "uv run pytest -q -m live_agent engineering/tests/e2e"

[tasks.test]
run = "uv run pytest -q -m 'not live_agent' && uv run ruff check tools tests engineering/tests && uv run ruff format --check tools tests engineering/tests"
```

Create `pyproject.toml` with Python `>=3.14,<3.15`, dependencies `PyYAML==6.0.3`, and dependency group `dev = ["pytest==9.1.1", "ruff==0.16.0"]`. Configure pytest with `testpaths = ["tests", "engineering/tests"]`, marker `live_agent`, and Ruff target `py314`, line length 100.

- [ ] **Step 2: Lock and bootstrap the environment**

Run:

```bash
mise install
mise exec -- uv lock
mise exec -- uv sync --frozen
mise exec -- vendir version
mise exec -- apm --version
```

Expected: vendir reports `v0.46.0`; APM reports `0.26.0`; `uv.lock` contains exact transitive resolutions.

- [ ] **Step 3: Write the failing vendir layout probe**

The test must initialize a temporary Git repository from `tests/fixtures/vendir-upstream`, rewrite the fixture's Git URL to that repository, run `vendir sync --chdir str(fixture_package)`, and assert:

```python
assert (skills / "alpha" / "SKILL.md").is_file()
assert (skills / "grilling" / "SKILL.md").is_file()
assert (skills / "setup-engineering-workflow-for-apm" / "SKILL.md").is_file()
assert not (skills / "setup-matt-pocock-skills").exists()
assert (skills / "audit-third-party-software" / "SKILL.md").read_text() == owned_text
assert os.access(skills / "alpha" / "scripts" / "run.sh", os.X_OK)
```

The fixture manifest must use one `directories` entry per imported leaf. Each
entry uses `includePaths` and `newRootPath` to select one exact upstream skill.
Map the upstream setup leaf to the final
`skills/setup-engineering-workflow-for-apm` destination and map `grilling`
from `skills/productivity/grilling`. Include a representative executable
script in the upstream fixture.

- [ ] **Step 4: Run the layout probe and capture the expected failure**

Run:

```bash
mise exec -- uv run pytest -q tests/adoption/test_vendir_layout.py
```

Expected before correcting the fixture: FAIL because collection-level ownership overwrites an owned sibling or leaves setup and `grilling` at their upstream paths.

- [ ] **Step 5: Correct the vendir composition, not the copied output**

Use one vendir manifest and lock. Declare one managed directory for every
imported upstream skill leaf. Owned skill directories are absent from the
manifest and remain untouched. Run unlocked sync followed by locked sync and
assert identical content, lock bytes, owned sentinel bytes, and executable
mode. The explicit leaf inventory is package acquisition policy; Python must
not copy or promote vendir output.

- [ ] **Step 6: Prove Renovate's artifact boundary**

`test_renovate_vendir.py` must run Renovate 43.285.7 in local dry-run mode against an older vendir lock, parse JSON logs, and assert the proposed artifact set includes:

```text
vendir.lock.yml
skills/alpha/SKILL.md
skills/grilling/SKILL.md
skills/setup-engineering-workflow-for-apm/SKILL.md
```

Then assert the hosted-safe configuration cannot invoke `python -m tools.capability_pack.cli update engineering` as part of the same atomic artifact update. Expected outcome: Renovate can commit vendir-managed files, but the required patch/provenance/qualification step needs self-hosted `postUpgradeTasks`; select the short scheduled GitHub workflow for Task 8.

Run:

```bash
mise exec -- uv run pytest -q tests/adoption
```

Expected: PASS. If Renovate can execute and commit the full qualification result without self-hosted unsafe commands, stop and revise Task 8 before continuing.

- [ ] **Step 7: Commit the adopted-tool boundary**

```bash
git add mise.toml pyproject.toml uv.lock .gitignore tests/adoption tests/fixtures/vendir-upstream tests/fixtures/vendir-package tests/fixtures/renovate
git commit -m "test: prove capability vendoring tool boundaries"
```

### Task 2: Implement staged qualification around vendir

**Files:**
- Create: `tools/capability_pack/__init__.py`
- Create: `tools/capability_pack/cli.py`
- Create: `tools/capability_pack/model.py`
- Create: `tools/capability_pack/qualify.py`
- Create: `tools/capability_pack/provenance.py`
- Create: `tools/capability_pack/summary.py`
- Create: `tests/capability_pack/test_patches.py`
- Create: `tests/capability_pack/test_drift.py`
- Create: `tests/capability_pack/test_provenance.py`
- Create: `tests/capability_pack/test_atomicity.py`
- Create: `tests/capability_pack/test_cli.py`
- Create: `tests/fixtures/upstreams/mattpocock-skills/`

**Interfaces:**
- Produces: `main(argv: Sequence[str] | None = None) -> int`.
- Produces: `qualify(package_root: Path, mode: Literal["update", "locked"], summary_path: Path | None = None) -> QualificationResult`.
- Produces: `load_provenance(path: Path) -> Provenance` and `write_provenance(path: Path, provenance: Provenance) -> None`.
- Produces: exit `0` for success/current, `2` for usage/configuration, `3` for breaking drift, and `4` for reproduction/qualification failure.
- Consumes: vendir as the only payload-acquisition subprocess. The core
  qualification path implemented here does not call `git fetch` or `git
  clone`; Task 8 adds the bounded metadata-only inventory checkout.

- [ ] **Step 1: Write RED tests for patch ordering and path safety**

Tests must prove `patches/series` order is honored, a rejected patch leaves the real package byte-identical, absolute/traversing patch paths fail, and symlinks escaping the staged package fail.

Run:

```bash
mise exec -- uv run pytest -q tests/capability_pack/test_patches.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.capability_pack'`.

- [ ] **Step 2: Add the data model and CLI contract**

Define frozen dataclasses:

```python
@dataclass(frozen=True)
class FileHash:
    path: str
    sha256: str

@dataclass(frozen=True)
class Provenance:
    source_commit: str
    included_skills: tuple[str, ...]
    excluded_skills: tuple[str, ...]
    source_files: tuple[FileHash, ...]
    patch_files: tuple[FileHash, ...]
    license_files: tuple[FileHash, ...]
    output_files: tuple[FileHash, ...]

@dataclass(frozen=True)
class QualificationResult:
    changed: bool
    source_commit: str
    added_skills: tuple[str, ...]
    removed_skills: tuple[str, ...]
    summary: str
```

Implement CLI syntax:

```text
capability-pack update PACKAGE [--summary PATH]
capability-pack check PACKAGE [--summary PATH]
```

Map `update` to vendir refresh and atomic replacement; map `check` to locked staging plus byte comparison without mutation.

- [ ] **Step 3: Implement minimal patch and staging behavior**

`qualify()` must copy the whole package into a sibling temporary directory,
run the package's single vendir manifest with
`vendir sync --chdir str(staged_package)` for update or
`vendir sync -l --chdir str(staged_package)` for locked mode, read
newline-delimited relative patch paths from `patches/series`, and run each with:

```python
subprocess.run(
    ["git", "apply", "--check", patch_path],
    cwd=stage,
    check=True,
    timeout=30,
)
subprocess.run(
    ["git", "apply", patch_path],
    cwd=stage,
    check=True,
    timeout=30,
)
```

Validate every patch header path resolves below the staged package before invoking Git.

- [ ] **Step 4: Add RED inventory and ownership tests**

Cover:

- adding the `beta` leaf to the proposed manifest and fixture source makes it
  appear in `added_skills`;
- a missing or renamed previously imported skill returns exit `3`;
- a missing legal file returns exit `4`;
- all three owned sibling skill trees remain byte-identical;
- changing an imported file causes `check` to return exit `4`;
- changing only an import timestamp does not affect comparison.

Run:

```bash
mise exec -- uv run pytest -q tests/capability_pack/test_drift.py tests/capability_pack/test_atomicity.py
```

Expected: FAIL because drift and ownership checks are absent.

- [ ] **Step 5: Implement drift, provenance, and atomic replacement**

Derive imported inventory from the vendir manifest's declared destination
leaves and staged `skills/*/SKILL.md`. Compare it to `provenance.yml`. Allow
additions; reject any removal with a message naming the old skill and source
commit. Verify every undeclared sibling skill tree remains byte-identical.

Hash bytes with SHA-256 in sorted POSIX-path order. Serialize YAML with
`sort_keys=False`; do not write timestamps. Read every source SHA from the
single vendir lock and fail when Matt entries resolve to different commits.

After every check passes, replace the package with two same-filesystem renames:

1. `engineering` to a unique backup sibling;
2. staged package to `engineering`;
3. delete the backup only after the second rename;
4. restore the backup if the second rename fails.

Never mutate the real package in `check` mode.

- [ ] **Step 6: Implement deterministic update evidence**

`summary.py` must render:

- previous and proposed full source commits;
- added, removed, and changed skills;
- patch hashes and patch failures;
- license hashes and changes;
- non-live test command/result;
- proposed version: patch for content-only update, minor for added skill, and `BLOCKED` for removal/rename or setup-contract change.

Write the same bytes for the same inputs.

- [ ] **Step 7: Run the complete qualification unit suite**

```bash
mise exec -- uv run pytest -q tests/capability_pack
mise exec -- uv run ruff check tools tests/capability_pack
mise exec -- uv run ruff format --check tools tests/capability_pack
```

Expected: PASS.

- [ ] **Step 8: Commit the qualification command**

```bash
git add tools/capability_pack tests/capability_pack tests/fixtures/upstreams
git commit -m "feat: qualify vendir capability imports"
```

### Task 3: Define and import the engineering distribution

**Files:**
- Create: `engineering/vendir.yml`
- Create: `engineering/vendir.lock.yml`
- Create: `engineering/provenance.yml`
- Create: `engineering/patches/series`
- Create: `engineering/patches/mattpocock-skills/0001-use-apm-setup-skill.patch`
- Create: `engineering/LICENSES/mattpocock-skills/LICENSE`
- Create/replace: imported directories under `engineering/skills/`
- Create: `engineering/tests/test_contract.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `qualify(..., mode="update")`.
- Produces: complete imported inventory at the locked SHA plus the three existing owned skills.
- Produces: one ordered patch transforming imported setup into `setup-engineering-workflow-for-apm` and redirecting every setup reference.

- [ ] **Step 1: Write the failing package contract**

Assert the imported inventory maps every upstream
`skills/engineering/*/SKILL.md` directory to the same final name except
`setup-matt-pocock-skills`, which maps to
`setup-engineering-workflow-for-apm`, and adds `grilling`. Assert the three
owned skills remain present and no installed text contains
`/setup-matt-pocock-skills`.

Run:

```bash
mise exec -- uv run pytest -q engineering/tests/test_contract.py
```

Expected: FAIL because `wayfinder`, `grilling`, and provenance do not exist.

- [ ] **Step 2: Add the real vendir policy**

Configure one manifest against `https://github.com/mattpocock/skills.git` at
tracked ref `origin/main`. Declare one `directories` entry for each current
upstream engineering skill. Each entry owns only its final
`skills/<skill-name>` leaf and selects the exact upstream leaf with
`includePaths` and `newRootPath`. Map upstream
`skills/engineering/setup-matt-pocock-skills` to
`skills/setup-engineering-workflow-for-apm`. Add one leaf entry mapping
`skills/productivity/grilling` to `skills/grilling`, plus the legal-file
entry. These owned siblings are outside every vendir destination:

```text
skills/audit-third-party-software/**
skills/context-extractor/**
skills/operating-omnigent/**
```

Use the leaf-level layout proven in Task 1. Set
`minimumRequiredVersion: 0.46.0`. The generated lock must record the same full
Matt commit for every imported leaf.

- [ ] **Step 3: Author and verify the setup-reference patch**

Create a Git-format patch against the exact staged vendir output. It changes
the imported setup skill's frontmatter, content, and self-references to
`setup-engineering-workflow-for-apm`, and changes exact references in:

```text
skills/ask-matt/SKILL.md
skills/code-review/SKILL.md
skills/to-spec/SKILL.md
skills/to-tickets/SKILL.md
skills/triage/SKILL.md
skills/wayfinder/SKILL.md
```

The replacement name is `setup-engineering-workflow-for-apm`. Add the patch path to `engineering/patches/series`.

- [ ] **Step 4: Generate the first controlled payload**

Run:

```bash
mise run vendor-engineering
git diff -- engineering/vendir.lock.yml engineering/provenance.yml engineering/skills engineering/LICENSES
```

Expected: every lock entry resolves
`2ab958093e83e0ec752e6c1c5932da465bf23e0c`; all 17 upstream engineering
capabilities appear under their final names plus `grilling`; the three owned
skills are unchanged.

- [ ] **Step 5: Add repository editing rules**

Update root `CLAUDE.md` to identify imported engineering paths as generated and direct maintainers to `engineering/CLAUDE.md` once created. Do not describe implementation history.

- [ ] **Step 6: Prove locked reproduction and direct-edit detection**

```bash
mise run vendor-engineering-check
mise exec -- uv run pytest -q tests/capability_pack/test_provenance.py -k direct_edit
```

Expected: locked reproduction passes; the isolated direct-edit fixture is reported and fails without changing the real package.

- [ ] **Step 7: Commit the controlled import**

```bash
git add CLAUDE.md engineering/vendir.yml engineering/vendir.lock.yml engineering/provenance.yml engineering/patches engineering/LICENSES engineering/skills engineering/tests/test_contract.py
git commit -m "feat(engineering): import controlled upstream skills"
```

### Task 4: Complete the patched APM setup workflow

**Files:**
- Modify: `engineering/patches/mattpocock-skills/0001-use-apm-setup-skill.patch`
- Modify generated: `engineering/skills/setup-engineering-workflow-for-apm/SKILL.md`
- Create through patch: `engineering/skills/setup-engineering-workflow-for-apm/templates/project-guidance.md`
- Create through patch: `engineering/skills/setup-engineering-workflow-for-apm/templates/issue-tracker-github.md`
- Create: `engineering/tests/test_setup_skill.py`
- Create: `engineering/tests/fixtures/setup-project/`

**Interfaces:**
- Produces: the patched skill `setup-engineering-workflow-for-apm`.
- Writes before compilation only below `.apm/instructions/` and `docs/agents/`.
- Invokes exactly `mise run agent-sync` after showing the proposed source-file changes.

- [ ] **Step 1: Write RED setup ownership tests**

Tests must parse the skill and run its fixture protocol to assert:

```python
assert changed_roots <= {".apm/instructions", "docs/agents"}
assert "AGENTS.md" not in directly_written_files
assert "CLAUDE.md" not in directly_written_files
assert sync_commands == [["mise", "run", "agent-sync"]]
```

Also test a second setup run produces no diff and user-authored text outside markers `<!-- engineering-workflow:start -->` / `<!-- engineering-workflow:end -->` survives.

- [ ] **Step 2: Run the setup tests**

```bash
mise exec -- uv run pytest -q engineering/tests/test_setup_skill.py
```

Expected: FAIL because the imported setup adaptation is incomplete and its templates are absent.

- [ ] **Step 3: Complete the setup adaptation patch**

Build the patch against the exact locked vendir output; do not edit the
generated destination as its source of truth. The resulting skill must:

1. Inspect repository structure and existing `.apm/instructions/` and `docs/agents/`.
2. Default the tracker to GitHub Issues.
3. Show exact proposed paths and unified diffs.
4. Ask approval before writing project-owned source files.
5. Replace only its marked sections.
6. Run `mise run agent-sync`.
7. Report compiled/audit failure without writing compiled targets itself.

Its name and all self-references must be `setup-engineering-workflow-for-apm`.

- [ ] **Step 4: Run setup and contract tests**

```bash
mise exec -- uv run pytest -q engineering/tests/test_setup_skill.py engineering/tests/test_contract.py
mise run vendor-engineering-check
```

Expected: PASS.

- [ ] **Step 5: Commit the setup workflow**

```bash
git add engineering/patches/mattpocock-skills/0001-use-apm-setup-skill.patch engineering/provenance.yml engineering/skills/setup-engineering-workflow-for-apm engineering/tests/test_setup_skill.py engineering/tests/fixtures/setup-project
git commit -m "feat(engineering): add APM setup workflow"
```

### Task 5: Enforce GitHub Issue approval and resume

**Files:**
- Create: `engineering/patches/mattpocock-skills/0002-github-issue-batch.patch`
- Modify: `engineering/patches/series`
- Modify through patch: `engineering/skills/setup-engineering-workflow-for-apm/templates/issue-tracker-github.md`
- Create: `engineering/tests/test_github_issue_workflow.py`
- Create: `engineering/tests/fixtures/fake-gh`

**Interfaces:**
- Produces: deterministic marker `<!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->`.
- Produces: one review batch containing title, body, labels, blockers, and order for every issue.
- External-write boundary begins at the first `gh issue create`; approval must occur immediately before it.
- Resume queries markers before creation and records each confirmed issue URL.

- [ ] **Step 1: Write RED approval and partial-failure scenarios**

Use the fake `gh` executable to log invocations and simulate failure after issue two. Tests must prove:

- no `issue create` occurs before approval;
- rejection creates zero issues;
- approval creates in dependency order;
- rerun after partial failure searches deterministic markers and creates only missing issues;
- the output reports confirmed issue URLs.

Run:

```bash
mise exec -- uv run pytest -q engineering/tests/test_github_issue_workflow.py
```

Expected: FAIL because the GitHub template and imported ticket instructions do not define the boundary.

- [ ] **Step 2: Define the GitHub tracker protocol**

Add to the generated GitHub template through
`0002-github-issue-batch.patch`:

1. Render the complete numbered batch.
2. Compute `batch_sha256` from canonical titles, bodies, labels, blockers, and order.
3. Put the marker in each body.
4. Ask “Create these GitHub Issues now?” after the batch and before any mutating `gh` call.
5. On approval, search all issue states for each marker.
6. Reuse the existing issue URL when exactly one marker matches.
7. Stop on multiple matches.
8. Create only missing issues and print each confirmed URL immediately.
9. Wire sub-issue/blocking relationships only after issue identities exist.

- [ ] **Step 3: Patch imported ticket-producing workflows**

Patch `to-tickets` and `wayfinder` so GitHub Issues are the pack's default real tracker, batch review precedes issue creation, and they delegate creation/resume details to `docs/agents/issue-tracker.md`. Keep the setup-name patch separate.

Run:

```bash
mise run vendor-engineering
mise exec -- uv run pytest -q engineering/tests/test_github_issue_workflow.py engineering/tests/test_contract.py
```

Expected: PASS.

- [ ] **Step 4: Commit the GitHub Issues contract**

```bash
git add engineering/patches engineering/provenance.yml engineering/skills engineering/tests/test_github_issue_workflow.py engineering/tests/fixtures/fake-gh
git commit -m "feat(engineering): gate GitHub Issue publication"
```

### Task 6: Make `engineering` an independent APM and native package

**Files:**
- Create: `engineering/apm.yml`
- Modify: `engineering/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Create: `engineering/README.md`
- Create: `engineering/CLAUDE.md`
- Create: `engineering/CHANGELOG.md`
- Create: `engineering/tests/test_package_metadata.py`
- Create: `engineering/tests/test_consumer_e2e.py`
- Create: `engineering/tests/consumer/apm.yml`

**Interfaces:**
- Produces: APM package `engineering` version `0.2.0`, with no dependency on root `apm.yml`.
- Produces: one consumer dependency, `git: kzarzycki/agent-skills/engineering`, constrained to `^0.2.0`.
- Preserves: native Claude install `engineering@kzarzycki-agent-skills`.

- [ ] **Step 1: Write RED metadata and virtual-subdirectory tests**

Assert:

- `engineering/apm.yml` and `plugin.json` both report `0.2.0`;
- marketplace has exactly one `engineering` entry pointing to `./engineering`;
- the floating `mattpocock-skills` marketplace entry is absent;
- engineering has no dependency on `kzarzycki/dotagents`;
- APM installs the local `engineering/` package into both `.claude/skills` and `.agents/skills`;
- empty `HOME`, `CLAUDE_CONFIG_DIR`, and `CODEX_HOME` are sufficient.

Run:

```bash
mise exec -- uv run pytest -q engineering/tests/test_package_metadata.py engineering/tests/test_consumer_e2e.py
```

Expected: FAIL because `engineering/apm.yml` is absent and the floating marketplace entry remains.

- [ ] **Step 2: Add aligned package metadata**

Create `engineering/apm.yml`:

```yaml
name: engineering
version: 0.2.0
description: Project-scoped engineering workflows for coding agents
author: Krzysztof Zarzycki
targets:
  - claude
  - codex
dependencies:
  apm: []
  mcp: []
includes: auto
scripts: {}
```

Bump `plugin.json` to `0.2.0`, describe the purpose-level capability pack, and update the existing marketplace entry. Remove the direct floating `mattpocock-skills` marketplace entry.

- [ ] **Step 3: Prove local and virtual-subdirectory APM installation**

The E2E test must create a temporary Git origin containing this repository, configure the fixture with the single engineering virtual-subdirectory dependency, and run:

```text
apm install
apm compile --validate
apm audit --ci --no-policy
apm install --frozen
```

Assert every imported name from `engineering/provenance.yml` plus the three
owned skills appears under both target skill directories, and root private
dependencies never appear.

- [ ] **Step 4: Add package documentation and editing rules**

Document APM and Claude marketplace channels separately, generated imported
paths, owned sibling paths, `mise run vendor-engineering`, locked checking,
`engineering-v0.2.0`, and the removal of the floating Matt marketplace entry.
`engineering/CLAUDE.md` must require vendir-check before commits and list the
three owned skills plus the patched setup skill.

- [ ] **Step 5: Run package checks**

```bash
mise run test-engineering-package
mise run vendor-engineering-check
python3 -m json.tool engineering/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
```

Expected: PASS.

- [ ] **Step 6: Commit the independent package**

```bash
git add engineering/apm.yml engineering/.claude-plugin/plugin.json .claude-plugin/marketplace.json engineering/README.md engineering/CLAUDE.md engineering/CHANGELOG.md engineering/tests
git commit -m "feat(engineering): publish independent capability pack"
```

### Task 7: Add Claude/Codex and Wayfinder conformance

**Files:**
- Create: `engineering/tests/e2e/test_static_discovery.py`
- Create: `engineering/tests/e2e/test_live_claude.py`
- Create: `engineering/tests/e2e/test_live_codex.py`
- Create: `engineering/tests/e2e/prompts/discover-skill.txt`
- Create: `engineering/tests/e2e/prompts/wayfinder-orient.txt`
- Create: `engineering/tests/e2e/fixture-repository/`

**Interfaces:**
- Produces: `run_agent(agent: Literal["claude", "codex"], prompt: str, repo: Path) -> AgentResult`.
- `AgentResult` contains `exit_code: int`, `stdout: str`, `stderr: str`, and `evidence_paths: tuple[str, ...]`.
- Live tests use empty user config roots and never create real GitHub Issues.

- [ ] **Step 1: Write RED static discovery and extension-seam tests**

Assert both APM targets deploy identical skill-name sets, all relative references and scripts resolve, and adding a synthetic third target adapter changes neither `engineering/skills` nor the consumer dependency.

Run:

```bash
mise exec -- uv run pytest -q engineering/tests/e2e/test_static_discovery.py
```

Expected: FAIL until the fixture runner and adapter assertion exist.

- [ ] **Step 2: Implement the static conformance runner**

Build the fixture in a temporary home, install/compile with APM, enumerate target catalogs, and compare them to provenance. Keep target-specific paths in the test adapter; do not put Claude/Codex branches into skill content.

- [ ] **Step 3: Add protected live agent scenarios**

For each agent:

1. Explicitly invoke each expected skill and require its exact skill name in the activation trace.
2. Run the setup prompt and assert only `.apm/instructions/` and `docs/agents/` change before fixture compilation.
3. Run Wayfinder with `wayfinder-orient.txt`.
4. Require evidence from `README.md`, `src/domain.py`, and `tests/test_domain.py`.
5. Use a fake `gh` on `PATH` and reject issue creation in the prompt.

Skip with a clear reason when `CLAUDE_CODE_E2E=1` or `CODEX_E2E=1` and credentials are absent; do not silently pass.

- [ ] **Step 4: Run deterministic and live conformance**

```bash
mise exec -- uv run pytest -q engineering/tests/e2e/test_static_discovery.py
CLAUDE_CODE_E2E=1 mise exec -- uv run pytest -q -m live_agent engineering/tests/e2e/test_live_claude.py
CODEX_E2E=1 mise exec -- uv run pytest -q -m live_agent engineering/tests/e2e/test_live_codex.py
```

Expected: all configured runs PASS; Wayfinder output names all three evidence files.

- [ ] **Step 5: Commit conformance**

```bash
git add engineering/tests/e2e
git commit -m "test(engineering): qualify Claude Codex and Wayfinder"
```

### Task 8: Add weekly draft updates and package-scoped release checks

**Files:**
- Create: `.github/workflows/engineering-ci.yml`
- Create: `.github/workflows/engineering-upstream-check.yml`
- Create: `.github/workflows/engineering-tag-check.yml`
- Modify: `tools/capability_pack/qualify.py`
- Modify: `tests/capability_pack/test_drift.py`
- Create: `tests/automation/test_workflows.py`
- Create: `tests/automation/test_release_scope.py`
- Modify: `README.md`

**Interfaces:**
- Weekly updater invokes `mise run vendor-engineering -- --summary /tmp/engineering-update.md`.
- Refresh reconciles the upstream engineering directory inventory into
  deterministic leaf entries before vendir acquisition.
- Update PR is always draft and never automerged.
- Tag workflow accepts only `engineering-v0.2.0`-shaped package tags matching both package manifests.

- [ ] **Step 1: Write RED workflow-policy tests**

Parse workflow YAML and assert:

- weekly schedule plus `workflow_dispatch`;
- draft PR creation;
- no merge, release, or tag command in the updater;
- updater permissions are `contents: write` and `pull-requests: write` only in its PR job;
- CI uses `vendor-engineering-check`, non-live tests, metadata checks, and local APM E2E;
- tag workflow triggers only `engineering-v*`;
- every `uses:` value ends in a 40-character SHA;
- changing `research/.claude-plugin/plugin.json` or `workflow/.claude-plugin/plugin.json` fails release scope.

Add a local Git fixture test that starts from a manifest without `beta`, adds
`skills/engineering/beta/SKILL.md` in a new fixture commit, and asserts refresh:

- resolves the candidate full SHA;
- adds one sorted `skills/beta` vendir directory entry with the exact upstream
  leaf mapping;
- maps upstream setup to `skills/setup-engineering-workflow-for-apm`;
- pins staged acquisition to the candidate SHA while retaining `origin/main`
  in the committed manifest;
- reports `beta` in the inventory summary;
- produces identical manifest and payload bytes on a second refresh.

Delete or rename a configured fixture leaf and assert refresh stops with
breaking-drift evidence naming the leaf and candidate SHA. It must preserve the
committed manifest, lock, and payload.

Run:

```bash
mise exec -- uv run pytest -q tests/automation
```

Expected: FAIL because workflows do not exist.

- [ ] **Step 2: Add path-scoped CI**

Trigger on changes to `engineering/**`, `tools/capability_pack/**`, `tests/capability_pack/**`, `tests/automation/**`, `mise.toml`, `pyproject.toml`, `uv.lock`, marketplace metadata, root README, and root CLAUDE instructions. Run:

```text
mise install
uv sync --frozen
mise run vendor-engineering-check
mise run test
mise run test-engineering-package
```

- [ ] **Step 3: Add the weekly draft updater**

Use the scheduled workflow selected by Task 1. It must:

1. Check out without persisted credentials.
2. Install pinned mise tools.
3. Run `mise run vendor-engineering -- --summary
   /tmp/engineering-update.md`. Update mode resolves the candidate SHA,
   enumerates the temporary checkout, reconciles leaf entries, and runs vendir
   against that exact candidate.
4. Exit cleanly when no diff exists.
5. Run all non-live qualification.
6. Open or update one branch, `automation/engineering-upstream`.
7. Open a draft PR whose body is the generated summary.
8. Set `automerge` nowhere.

Do not call `gh pr merge`, `git tag`, or `gh release create`.

- [ ] **Step 4: Add package-tag validation**

On `engineering-v*`, extract the tag version, compare it to both `engineering/apm.yml` and `plugin.json`, run locked reproduction/package/conformance checks, and fail if any other top-level plugin manifest changed in the tagged commit. A Git tag is the APM release; do not add a repository-wide version.

- [ ] **Step 5: Update root documentation**

Describe `agent-skills` as a distribution monorepo with independent capability packs, add the APM project dependency for `engineering`, retain native Claude installation instructions, document package-scoped tags, and state imported payloads are generated by vendir plus qualification.

- [ ] **Step 6: Run workflow and full non-live verification**

```bash
mise exec -- uv run pytest -q tests/automation
mise run vendor-engineering-check
mise run test
mise run test-engineering-package
git diff --check
git status --short
```

Expected: tests PASS; status contains only the intentional Task 8 changes before commit.

- [ ] **Step 7: Commit automation**

```bash
git add .github/workflows tests/automation README.md
git commit -m "ci(engineering): qualify updates and package tags"
```

#### Release-candidate audit

**Files:**
- Modify only if a failing verification identifies a defect in a Stage 1 file.

**Interfaces:**
- Consumes every interface above.
- Produces a reviewed `engineering-v0.2.0` candidate; creating the tag remains a human action outside this plan.

- [ ] **Step 8: Reconstruct from the locked source**

```bash
mise run vendor-engineering-check
git diff --exit-code -- engineering/skills engineering/vendir.lock.yml engineering/provenance.yml engineering/LICENSES
```

Expected: PASS and no diff.

- [ ] **Step 9: Run all deterministic checks**

```bash
mise run test
mise run test-engineering-package
python3 -m json.tool engineering/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
git diff --check
```

Expected: PASS.

- [ ] **Step 10: Run both protected agent suites**

```bash
CLAUDE_CODE_E2E=1 mise exec -- uv run pytest -q -m live_agent engineering/tests/e2e/test_live_claude.py
CODEX_E2E=1 mise exec -- uv run pytest -q -m live_agent engineering/tests/e2e/test_live_codex.py
```

Expected: PASS with recorded skill-discovery, setup, and Wayfinder evidence.

- [ ] **Step 11: Inspect security and release evidence**

Review:

```bash
git diff main...HEAD -- engineering/skills engineering/patches engineering/LICENSES
git diff main...HEAD -- .github/workflows engineering/apm.yml engineering/.claude-plugin/plugin.json
git log --oneline main..HEAD
git status --short
```

Confirm the source SHA, licenses, external commands, authentication assumptions, issue-write boundary, workflow permissions, and proposed `0.2.0` classification.

- [ ] **Step 12: Request independent review**

Use `superpowers:requesting-code-review` against the approved spec, with explicit checks for R1–R5, R11–R26 and AC1–AC2, AC6–AC19, AC22–AC24. AC3–AC5 and AC20–AC21 remain Stage 2 because they require the Copier-owned `agent-sync` implementation.

- [ ] **Step 13: Commit any review fixes and leave tagging to the maintainer**

After rerunning the affected tests:

```bash
git add engineering tools/capability_pack tests .github/workflows mise.toml pyproject.toml uv.lock README.md CLAUDE.md .claude-plugin/marketplace.json .gitignore
git commit -m "fix(engineering): address capability pack review"
git status --short
```

Expected: clean working tree. Do not create `engineering-v0.2.0`; report that the human release gate is ready.

## Stage 1 Coverage

- R1–R5: Tasks 3, 6, and 7.
- R11–R18: Tasks 1–3.
- R19–R20: Tasks 3–4.
- R21: Task 5.
- R22: Task 7.
- R23–R25: Task 8.
- R26 Stage 1 qualification: Tasks 6–8.
- R6–R10 and consumer `agent-sync` AC3–AC5 belong to Stage 2; Task 6 supplies the local package fixture and one-dependency contract needed by that session.
- AC20–AC21 belong to the `project-templates` plan. AC22–AC24 are covered here by empty user config, adapter seam, and draft-only automation.
