# update-delta-audit spike spec

## Goal
Create a portable skill for cheap pre-install audits of software update prompts. The skill answers one question: "is this update safe enough to install now?" It audits the delta between the installed version and the candidate version, not the entire product.

## Non-goals
- Full third-party software audit.
- Installing or executing the update.
- Proving every binary is reproducibly built unless the upstream already publishes enough data to do so cheaply.
- Reviewing unchanged application code unrelated to update/install/runtime privilege surfaces.

## Primary form
A skill named `update-delta-audit`.

Reason: a skill is portable across CLIs, desktop apps, package managers, and vendor-specific update flows. It can instruct the agent to use existing tools (`read`, `search`, `web_search`, `bash` only for safe metadata commands) without coupling to OMP/GSD experiment code.

## Trigger examples
Use the skill when the user asks whether to install a prompted update, especially:

1. OMP CLI example: the user is running OMP and sees: `New version 15.10.4 is available. Run: omp update`. They want a quick check of the diff between the current installed version and `15.10.4`, plus assurance that binaries installed by `omp update` match the published code/provenance.
2. Orca StablyAI macOS example: the user is running the Orca StablyAI macOS app and sees: `update available version Xyz`. They want the same check: current app vs candidate, updater procedure, downloaded artifact, code signing/notarization, and binary provenance.

## Workflow
1. Capture current state:
   - software name
   - installed version
   - candidate version
   - operating system and install channel
   - updater command or update prompt text
2. Identify update mechanism without installing:
   - package manager, self-updater, Sparkle/Appcast, GitHub release, npm/bun/pnpm package, Homebrew cask, vendor feed, or app-specific endpoint
   - commands the updater would run
   - URLs/artifacts it would fetch
3. Fetch metadata/artifacts to an isolated audit directory:
   - release notes/changelog
   - source tag or commit for current and candidate version
   - package manifests and lockfiles
   - installer/updater scripts
   - binary archives, app bundles, checksums, signatures, attestations
4. Diff changed/high-risk surfaces only:
   - updater/install scripts
   - dependency manifests and lockfiles
   - new or changed binaries
   - privilege/permission changes
   - network/update endpoints
   - postinstall/preinstall hooks
   - macOS entitlements, Team ID, notarization, hardened runtime
   - CI/release workflow changes that affect artifact production
5. Classify findings:
   - `SAFE`: expected release delta, provenance/signing checks pass, no changed high-risk update surface.
   - `CAUTION`: provenance incomplete, binary/source correspondence cannot be cheaply proven, benign but material updater/dependency changes, or unclear vendor metadata.
   - `BLOCK`: changed updater path with unexplained network/install behavior, signature/checksum mismatch, unsigned or wrongly signed app, new obfuscated installer logic, unexpected credential/dotfile access, or artifact not traceable to expected upstream.
6. Report with evidence:
   - verdict
   - exact versions compared
   - updater mechanism
   - artifacts fetched with SHA-256
   - changed surfaces reviewed
   - findings with file/URL/metadata citations
   - install recommendation

## Output format

```markdown
## Verdict: SAFE | CAUTION | BLOCK
One-sentence reason.

## Compared
- Software:
- Current version:
- Candidate version:
- Install/update channel:
- Audit directory:

## Update mechanism
What would install the update, what it fetches, and what was not executed.

## Delta reviewed
Bullets for changed updater/install/dependency/binary/permission/network surfaces.

## Findings
Only findings that affect the verdict. Include citations and hashes.

## Provenance checks
Checksums, signatures, notarization, registry metadata, source tag/build metadata. State gaps explicitly.

## Recommendation
Install / do not install / ask vendor for missing provenance.
```

## Cheapness rules
- Prefer metadata and targeted diffs over whole-repo reading.
- Stop expanding scope when changed surfaces are accounted for.
- Escalate to `audit-third-party-software` only when the delta introduces a new updater, installer, binary runtime, hidden network path, or privilege boundary that cannot be explained locally.
- Do not run the updater or installer.
- Do not execute candidate binaries.

## Skill package shape

```text
update-delta-audit/
  SKILL.md
  references/
    updater-patterns.md
    report-template.md
  scripts/
    hash-artifact.py
    macos-app-provenance.sh
```

`SKILL.md` should stay short and route platform-specific details to references. Scripts should be deterministic helpers only; the skill remains useful even when scripts are unavailable.

## Spike acceptance
- Draft `update-delta-audit/SKILL.md` with the cheap delta-audit workflow.
- Include OMP and Orca/StablyAI examples as explicit examples/evals.
- Include at least three eval prompts:
  1. OMP `15.10.4` update prompt.
  2. Orca StablyAI macOS app update prompt.
  3. A package-manager update with unchanged updater path and changed lockfile.
- The skill must produce reports that avoid full-audit scope unless escalation criteria are met.
