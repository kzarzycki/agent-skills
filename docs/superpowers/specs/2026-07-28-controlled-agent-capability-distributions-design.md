# Controlled Agent Capability Distributions

**Status:** Approved design
**Date:** 2026-07-28
**Owner:** `kzarzycki/agent-skills`

## Part 1 — Product

### Outcome

`agent-skills` distributes reusable agent workflows as independently versioned capability packs. A repository selects a pack with one APM dependency and converges its agent configuration with one mise operation:

```sh
mise run agent-sync
```

The first controlled distribution is the `engineering` capability pack. It contains the current engineering skills from `mattpocock/skills`, their `grilling` dependency, and project-integration behavior owned by this repository. Claude Code and Codex use the same project-scoped skill payload. Copier adds the dependency and sync task to new repositories.

The model supports solo repositories and company baselines. Repository configuration remains sufficient on a clean machine, in CI, and in remote agent environments. User-level installations may provide personal convenience without becoming a project dependency.

### Terms

- **Skill:** one Agent Skills workflow rooted at `SKILL.md`.
- **Capability pack:** an independently installable and versioned collection of related skills, optional agent-specific plugin manifests, tests, provenance, and integration behavior.
- **Plugin:** an agent-native installable bundle. Claude and Codex plugin manifests are distribution adapters for a capability pack.
- **Controlled vendoring:** deterministic import of selected upstream files at an exact commit, followed by an explicit patch set and provenance recording.
- **Consumer repository:** a project that declares and installs a capability pack.
- **Source repository:** an upstream repository from which skills are imported.

### Users

#### Repository contributor

A contributor clones a project, runs `mise run agent-sync`, and receives the skills and generated configuration selected by that repository.

#### Solo maintainer

A maintainer opts a repository into a capability pack, refreshes dependencies when desired, and commits the resulting manifest and lock changes.

#### Company platform maintainer

A platform maintainer selects approved capability packs in a Copier template or company baseline. Dependency update pull requests propagate qualified releases to repositories.

#### Capability-pack maintainer

A maintainer reviews upstream changes, local integration patches, licenses, compatibility checks, and package-scoped releases in `agent-skills`.

### Scope

This design covers:

- the `agent-skills` repository as a public distribution monorepo;
- independently versioned capability packs organized by user purpose;
- controlled vendoring from multiple public source repositories;
- APM as the canonical project installation path;
- native plugin manifests as agent-specific distribution adapters;
- mise as the single task entry point in consumer repositories;
- Claude Code and Codex compatibility in the first release;
- extension points for GitHub Copilot and Cursor;
- Copier scaffolding for new repositories;
- project-scoped adoption by existing repositories and dotagents;
- weekly upstream detection, qualification, and package releases.

Private company skills belong in a repository with matching access control. Machine profiles, secrets, MCP credentials, CLI authentication, and endpoint selection remain in the repository agent-layer system defined outside this package.

### Requirements

#### Distribution

**R1 — One consumer dependency.** A consumer selects the `engineering` capability pack with one APM dependency. Upstream repositories, selected paths, commits, and integration patches remain internal to the pack.

**R2 — Independent packages.** Each top-level capability pack has its own APM package root, version, release tag, tests, provenance, and changelog. Releasing one pack does not require releasing another.

**R3 — Purpose-based composition.** Capability packs are organized by consumer purpose such as `engineering`, `research`, or `workflow`. One pack may import skills from several source repositories.

**R4 — Portable skill payload.** Imported and owned skills use the Agent Skills directory format. The same payload can be compiled or adapted for multiple coding agents.

**R5 — Agent adapters.** A capability pack may expose Claude or Codex plugin manifests without making either manifest the canonical source. New coding-agent support is added as an adapter and conformance test.

#### Consumer operation

**R6 — One idempotent operation.** `mise run agent-sync` is the sole public convergence operation.

**R7 — Resolution modes.** The operation supports:

- default convergence against the committed manifest and lock;
- `--refresh` to resolve available dependency releases before convergence;
- `--frozen` to verify committed manifests, locks, and compiled output.

**R8 — Project ownership.** A repository commits its APM manifest, lock, APM instruction sources, and required generated agent configuration according to the repository agent-layer contract.

**R9 — Clean-environment operation.** A consumer works without dotagents, a global Matt plugin, or a global Superpowers installation. Superpowers remains an independently selected dependency.

**R10 — Solo and company adoption.** The same package and sync contract work in a manually configured repository and a Copier-generated company repository.

#### Controlled vendoring

**R11 — Exact source resolution.** Every vendored file maps to a source repository, full Git commit, selected path, and recorded file hash.

**R12 — Reproducible generation.** Re-running vendoring from the recorded sources and patches reproduces the committed payload byte for byte.

**R13 — Generated imports.** Vendored files are generated artifacts. Maintainers change the source selection, source commit, or patch set rather than editing imported files directly.

**R14 — Explicit local behavior.** Repository-owned skills live beside imported skills and have distinct names. Replacement or adaptation skills do not shadow an upstream skill name.

**R15 — Bounded patches.** Integration changes are represented as ordered, reviewable patches. A source moves to a fork or an owned skill when the patch set becomes a maintained product branch.

**R16 — License preservation.** Each source retains the license, notices, attribution, and redistribution conditions required for its imported files.

**R17 — Safe source drift.** New matching upstream skills appear in a reviewable update pull request. Removal, rename, patch failure, or license change stops publication and requires a maintainer decision.

#### Matt engineering distribution

**R18 — Engineering inventory.** The first `engineering` release imports every current `skills/engineering/*/SKILL.md` capability from `mattpocock/skills` except `setup-matt-pocock-skills`, plus `skills/productivity/grilling`.

**R19 — APM setup skill.** The upstream `setup-matt-pocock-skills` payload is excluded. The pack supplies `setup-engineering-workflow-for-apm`, which writes project-owned instruction sources under `.apm/instructions/` and repository guidance under `docs/agents/`.

**R20 — Generated-file discipline.** The setup skill does not edit compiled `AGENTS.md`, `CLAUDE.md`, or other agent targets directly. It invokes the standard compile and audit path after changing source files.

**R21 — GitHub Issues workflow.** Ticket-producing workflows target GitHub Issues. They prepare a reviewable issue batch and request approval immediately before issue creation.

**R22 — Wayfinder priority.** Wayfinder is present, discoverable, and covered by an end-to-end repository-orientation scenario in Claude Code and Codex.

#### Updates and releases

**R23 — Weekly detection.** Scheduled automation checks each recorded source against its configured upstream ref at least weekly.

**R24 — Draft update pull request.** A detected change produces a draft pull request containing source commits, inventory changes, patches, licenses, generated diffs, test results, and a proposed package version.

**R25 — Human release gate.** Automation does not merge an upstream refresh or publish a package release. A maintainer approves the diff and creates the package-scoped tag.

**R26 — Consumer qualification.** A capability-pack release must pass clean installation, frozen reinstall, agent discovery, setup, idempotence, and Copier end-to-end checks before publication.

### User workflows

#### New Copier repository

1. The user enables coding-agent support in the Copier answers.
2. Engineering workflow support is enabled by default and may be disabled.
3. Copier renders the APM dependency, lock, mise task, and agent-layer source configuration.
4. The user runs `mise run agent-sync`.
5. Claude Code and Codex discover the selected skills.

#### Existing repository

1. The maintainer applies the standard agent-layer scaffold from the Copier template.
2. The maintainer enables the `engineering` capability-pack dependency.
3. The maintainer runs `mise run agent-sync`.
4. The maintainer invokes `setup-engineering-workflow-for-apm` when the repository has enough structure to analyze.
5. The maintainer reviews and commits the project-owned instruction sources and generated outputs.

#### Normal convergence

```sh
mise run agent-sync
```

The operation validates configuration, resolves only when the manifest or lock requires it, installs locked dependencies, compiles agent targets, audits the result, and exits without a diff when the repository is current.

#### Intentional refresh

```sh
mise run agent-sync -- --refresh
```

The operation resolves available capability-pack releases, updates the lock, installs, compiles, audits, and leaves a reviewable repository diff.

#### CI verification

```sh
mise run agent-sync -- --frozen
```

The operation installs exactly the committed lock and fails when dependency resolution, compilation, or audit would change committed state.

#### Upstream refresh

1. Scheduled automation observes a new source commit.
2. The vendoring tool builds the proposed capability pack in a temporary directory.
3. It imports selected files, applies patches, records provenance, and runs checks.
4. It opens a draft pull request after successful generation.
5. A maintainer reviews upstream behavior, supply-chain risk, licenses, and compatibility.
6. The maintainer selects the semantic version and merges the pull request.
7. The maintainer publishes a package-scoped tag.
8. Consumer repositories receive or request the new package release and verify it with `agent-sync --frozen`.

## Part 2 — Architecture

### Repository model

`agent-skills` is one Git repository containing several package roots:

```text
agent-skills/
├── engineering/
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   ├── wayfinder/
│   │   ├── tdd/
│   │   ├── grilling/
│   │   └── setup-engineering-workflow-for-apm/
│   ├── apm.yml
│   ├── vendor.yml
│   ├── vendor.lock.yml
│   ├── patches/
│   ├── LICENSES/
│   └── tests/
├── research/
├── workflow/
└── shared release and vendoring automation
```

The existing top-level plugin layout remains the package boundary. `engineering/`, `research/`, and `workflow/` are independently installable and versioned. Shared automation operates on a selected package path and leaves package policy inside that package.

### Capability-pack contract

A capability-pack root contains:

- an APM manifest declaring the portable package;
- a `skills/` directory containing imported and owned Agent Skills;
- a native Claude plugin manifest when Claude marketplace installation is supported;
- a native Codex plugin manifest when that installation channel is supported and tested;
- vendoring policy and resolved provenance for imported files;
- local patches and source licenses;
- package-specific conformance tests.

APM is the project installation contract. Native plugin metadata adds discovery and installation channels for a specific agent. Consumers using APM receive repository-scoped skills whether or not a native plugin browser is present on that agent surface.

### Consumer dependency

A consumer references the capability-pack package root and a compatible package release:

```yaml
dependencies:
  apm:
    - git: kzarzycki/agent-skills/engineering
      ref: ^0.2.0
```

The consumer lock records the exact resolved package release and Git commit. Package-prefixed Git tags, such as `engineering-v0.2.0`, provide independent releases from the monorepo.

### Vendoring policy

`vendor.yml` is reviewed policy. For each source it declares:

- stable source identifier;
- canonical Git URL;
- tracked ref used for update detection;
- include rules;
- exclude rules;
- required support paths;
- ordered patch series;
- license and notice paths.

Conceptual example:

```yaml
sources:
  - id: mattpocock-skills
    git: https://github.com/mattpocock/skills.git
    track: refs/heads/main
    include:
      - skills/engineering/*/SKILL.md
      - skills/engineering/*/**
      - skills/productivity/grilling/**
    exclude:
      - skills/engineering/setup-matt-pocock-skills/**
    patches:
      - patches/mattpocock-skills/0001-apm-setup-references.patch
      - patches/mattpocock-skills/0002-github-issues-target.patch
```

`vendor.lock.yml` is generated provenance. It records:

- resolved full commit;
- import timestamp used for audit only;
- included and excluded skill inventory;
- source-to-destination path mapping;
- source hashes;
- applied patch hashes;
- license hashes;
- generated payload hashes.

Volatile timestamps do not participate in payload comparison. Reproduction compares source identity, patches, paths, and content.

### Vendoring algorithm

The vendoring operation:

1. Validates `vendor.yml`.
2. Fetches each allowed source and checks out the resolved commit.
3. Discovers paths matching the include and exclude policy.
4. Compares the discovered skill inventory with the previous lock.
5. Stops for upstream removals or renames.
6. Copies selected files into a temporary package tree.
7. Applies the ordered patch set.
8. Adds repository-owned skills and metadata.
9. Copies required licenses and notices.
10. Generates provenance and content hashes.
11. Runs package tests against the temporary tree.
12. Compares the result with the committed package.
13. Replaces generated paths only after successful validation.

Fetch, patch, license, or test failure leaves the committed capability pack unchanged.

### Imported and owned files

Every skill has one ownership class:

- **Imported:** reproduced from an upstream commit and patch set.
- **Owned:** authored and maintained in `agent-skills`.

Imported files are verified by reconstruction. Owned files are excluded from vendored payload replacement and follow normal repository review.

Small interoperability changes belong in source-specific patches. A patch that develops independent behavior is replaced by an owned skill with a distinct name. A large, persistent set of upstream modifications moves to a dedicated fork and retains the same capability-pack consumer contract where possible.

### Engineering integration behavior

The `engineering` pack imports all current Matt engineering skills and `grilling`. The inventory is discovered from upstream rather than duplicated in consumer repositories.

The owned `setup-engineering-workflow-for-apm` skill:

- inspects repository structure and existing agent-layer sources;
- writes project-specific guidance under `.apm/instructions/`;
- writes durable project documentation under `docs/agents/`;
- preserves user-authored content outside its owned sections;
- invokes `agent-sync` for compilation and audit;
- explains every proposed file change before applying it.

References from imported skills to Matt’s upstream setup workflow are changed through the recorded APM integration patch. The resulting installed skill catalog contains `setup-engineering-workflow-for-apm` and does not contain a local replacement named `setup-matt-pocock-skills`.

Ticket generation targets GitHub Issues. The workflow builds titles, bodies, labels, dependencies, and ordering as a review batch. It asks for approval at the external-write boundary and creates issues only after approval. Re-running after partial creation detects existing issues or records sufficient state to avoid silent duplicates.

### `agent-sync` state machine

The mise task delegates to one implementation with three resolution policies.

#### Default

1. Validate the APM manifest and existing lock.
2. Create a lock when absent.
3. Reconcile the lock when the manifest changed.
4. Install the resolved lock.
5. Compile every configured coding-agent target.
6. Audit generated files and required environment declarations.
7. Return success only when the repository is converged.

#### Refresh

`--refresh` allows dependency resolution against declared version ranges before following the default convergence pipeline. It does not bypass compatibility, compile, or audit checks.

#### Frozen

`--frozen` requires a present, current lock and committed compiled state. It installs exact resolutions, runs compile and audit checks, and fails on any resulting diff.

Unknown flags and incompatible mode combinations return a usage error. Failures identify the phase, affected package or target, and next corrective action.

### Agent compatibility

The first release supports Claude Code and Codex.

Conformance is defined by observable outcomes:

- the agent discovers every expected skill;
- explicit invocation resolves the intended skill;
- implicit selection can match representative prompts;
- skill references and scripts resolve from the installed location;
- setup writes project sources and compilation produces valid agent targets;
- no user-level plugin state is required.

GitHub Copilot and Cursor support is added by implementing their APM target or repository adapter and running the same conformance suite. Capability-pack contents and consumer dependency syntax remain unchanged.

### Release policy

Each capability pack uses semantic versions and package-prefixed tags:

- patch: upstream content refresh with the same public skill inventory and consumer contract;
- minor: added public skill or compatible new capability;
- major: removed or renamed skill, incompatible setup behavior, or changed consumer contract.

An automated update may propose a version. The reviewer owns the final classification.

The release workflow accepts a package path, verifies that path and its dependencies, and publishes its tag. Path-scoped CI prevents unrelated capability packs from blocking a release while shared infrastructure changes run the full matrix.

### Security and trust

Controlled vendoring treats upstream skill changes as executable workflow changes. Review covers instructions, scripts, referenced commands, network behavior, external writes, authentication expectations, and newly added files.

Source URLs are allowlisted. Full commits and hashes prevent branch movement after review. Update workflows use read-only source credentials and the minimum repository permission needed to open a draft pull request. Release credentials are available only to the human-gated release job.

Capability packs with different visibility, maintainers, security policy, licensing constraints, or incident boundaries move to separate repositories. Private company payload stays outside the public `agent-skills` repository.

### Failure handling

- **Source unavailable:** report the source and preserve the existing pack.
- **New matching skill:** include it in the draft diff and require inventory review.
- **Removed or renamed skill:** stop generation and require a compatibility decision.
- **Patch rejected:** report the patch and conflicting upstream paths; preserve the existing pack.
- **License changed or missing:** block release pending review.
- **Reproduction mismatch:** fail CI and identify differing files.
- **Agent conformance failure:** block the package release for the affected supported agent.
- **Consumer frozen mismatch:** fail with the manifest, lock, or compiled files that require regeneration.
- **Partial GitHub issue creation:** report created issue URLs and resume without duplicating confirmed issues.

## Part 3 — Verification

### Acceptance criteria

**AC1 — One dependency.** A fixture repository enables the engineering pack through one APM dependency on `agent-skills/engineering`.

**AC2 — Clean installation.** The fixture installs on a clean machine with repository-declared prerequisites and no user-level Matt, Superpowers, or dotagents state.

**AC3 — Idempotence.** Running `mise run agent-sync` twice succeeds and the second run changes no tracked file.

**AC4 — Refresh.** Given a newer compatible engineering release, `mise run agent-sync -- --refresh` updates the lock, compiles both supported targets, passes audit, and reaches a clean second run.

**AC5 — Frozen verification.** `mise run agent-sync -- --frozen` succeeds for committed current state and fails for a stale manifest, stale lock, or stale compiled target.

**AC6 — Claude discovery.** Claude Code discovers and can explicitly invoke every expected engineering skill from the fixture.

**AC7 — Codex discovery.** Codex discovers and can explicitly invoke every expected engineering skill from the fixture.

**AC8 — Complete Matt inventory.** The generated engineering pack contains every current upstream `skills/engineering/*` skill except `setup-matt-pocock-skills`, plus `grilling`.

**AC9 — Distinct setup.** The installed catalog contains `setup-engineering-workflow-for-apm` and contains no locally substituted skill using the upstream setup name.

**AC10 — Setup ownership.** Running the setup skill changes only `.apm/instructions/` and `docs/agents/` before compilation.

**AC11 — Compiled-file protection.** A test fails if the setup skill writes directly to compiled Claude or Codex instruction targets.

**AC12 — Wayfinder scenario.** In both Claude Code and Codex, Wayfinder orients itself in a representative rendered repository and returns evidence from the expected project files.

**AC13 — GitHub Issues approval.** A ticket workflow produces a review batch, pauses immediately before creation, and creates no issue without approval.

**AC14 — GitHub Issues resume.** A simulated partial issue-creation failure resumes without duplicating already confirmed issues.

**AC15 — Reproducible vendoring.** Reconstructing the engineering pack at the locked upstream commit yields the committed imported payload and provenance hashes.

**AC16 — Direct-edit detection.** Modifying an imported file without changing its source or patch causes reproduction CI to fail.

**AC17 — New upstream skill.** A fixture source addition appears in the generated draft update and inventory summary.

**AC18 — Breaking upstream drift.** A fixture removal, rename, rejected patch, or missing license blocks publication and preserves the last committed package.

**AC19 — Independent release.** Publishing an engineering tag does not change or release any other capability pack.

**AC20 — Copier enabled render.** Copier renders a repository with the engineering dependency and a passing frozen end-to-end test.

**AC21 — Copier disabled render.** Copier renders a repository without the engineering dependency and retains a passing base agent-layer end-to-end test.

**AC22 — Project scope.** The end-to-end fixtures pass with empty Claude and Codex user configuration directories.

**AC23 — Agent extension seam.** A conformance fixture can add another coding-agent adapter without changing the capability-pack payload or consumer dependency.

**AC24 — Draft-only upstream automation.** Scheduled source detection can open a draft pull request but cannot merge it or publish a release.

### Requirement traceability

| Requirement | Acceptance criteria |
|---|---|
| R1 | AC1 |
| R2–R3 | AC19 |
| R4–R5 | AC6, AC7, AC23 |
| R6–R7 | AC3–AC5 |
| R8–R10 | AC2, AC20–AC22 |
| R11–R13 | AC15, AC16 |
| R14–R15 | AC9, AC16, AC18 |
| R16–R17 | AC17, AC18 |
| R18 | AC8 |
| R19–R20 | AC9–AC11 |
| R21 | AC13, AC14 |
| R22 | AC12 |
| R23–R25 | AC17, AC18, AC24 |
| R26 | AC2–AC12, AC15, AC20–AC22 |

### Rollout

#### Stage 1 — Engineering capability pack

Add the package root, controlled-vendoring metadata, Matt import, owned APM setup skill, conformance fixtures, and package-scoped release path to `agent-skills`.

#### Stage 2 — Project template

Add the engineering dependency option and the single `agent-sync` operation to `project-templates`. Qualify enabled and disabled Copier renders.

#### Stage 3 — Repository adoption

Adopt the released capability pack in selected existing repositories, then in dotagents as an ordinary project-scoped consumer. Remove reliance on the legacy user-global Matt installation after repository adoption is verified.

#### Stage 4 — Additional sources and agents

Add controlled sources to existing purpose-based packs or create a new pack when the consumer purpose differs. Add GitHub Copilot and Cursor through agent adapters and the shared conformance suite.

### Completion condition

The V2 rollout is complete when:

- `engineering` is a released, independently versioned capability pack;
- its vendored Matt payload is reproducible and qualified;
- a clean Copier project installs it through one dependency;
- `agent-sync` converges idempotently in default, refresh, and frozen modes;
- Claude Code and Codex pass discovery, setup, Wayfinder, and GitHub Issues scenarios;
- weekly automation opens reviewable upstream update pull requests;
- dotagents and global plugin state are absent from the consumer acceptance environment.
