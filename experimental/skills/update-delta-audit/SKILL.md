---
name: update-delta-audit
description: Use when a user sees a software update prompt, "new version available", "run <tool> update", app updater notice, package-manager upgrade notice, or asks whether an already-installed/trusted tool is safe to update before installing.
---

# Update Delta Audit

## Overview
Cheap pre-install update audit. Answer whether this specific update is safe enough to install by checking changed update/install/provenance surfaces, not by auditing the whole product.

## Core rule
Do not run the updater, installer, or candidate binary. Fetch metadata/artifacts only, hash them, inspect updater mechanics, and report `SAFE / CAUTION / BLOCK`.

## Quick reference
| Situation | Read next | Key checks |
|---|---|---|
| CLI/package update | `references/updater-patterns.md` | registry metadata, tarball hash, scripts, lockfile/deps, release tag |
| GitHub binary release | `references/updater-patterns.md` | tag commit, release run, CI artifact zip digest, contained binary hash, release asset hash |
| macOS app update | `references/updater-patterns.md` | appcast/feed, code signing, Team ID, notarization, entitlements |
| Need final report | `references/report-template.md` | fixed evidence-backed report shape |

## Workflow
1. Capture software, installed version, candidate version, OS, install channel, and exact prompt/command.
2. Identify updater mechanism without installing: package manager, self-updater, Sparkle/appcast, GitHub release, Homebrew, vendor feed.
3. Fetch candidate metadata/artifacts into an isolated audit dir. Record SHA-256 for every artifact; use `scripts/hash-artifact.py` if helpful.
4. For GitHub release binaries, try practical CI provenance before declaring source/binary correspondence unproven: map release tag to commit, find the release workflow run, download the matching CI artifact when available, verify its digest against GitHub Actions metadata/logs, hash the contained raw binary, and compare byte-for-byte with the release asset. If CI artifacts are not available, inspect release job logs for tag checkout, build command, upload line, uploader identity, asset created/updated timestamps, and final publish/un-draft job; report this as corroborating provenance, not cryptographic proof.
5. Diff only changed/high-risk surfaces: updater/install scripts, lockfiles/dependencies, new binaries, permissions/entitlements, network/update endpoints, release workflow/provenance.
6. Stop when changed surfaces are accounted for. Escalate to a full third-party audit only if the delta introduces an unexplained updater, installer, binary runtime, hidden network path, credential/dotfile access, or privilege boundary.
7. Report using only `SAFE`, `CAUTION`, or `BLOCK`.

## Verdicts
- `SAFE`: version/hash-only delta or reviewed code delta, no changed updater/install/permission/network surface, and signatures/provenance/checksums match. For GitHub release binaries, byte-for-byte match between release asset and CI artifact from the reviewed tag's successful release run is acceptable practical provenance when stronger attestations are absent.
- `CAUTION`: provenance incomplete, binary/source correspondence not cheaply provable, GitHub CI artifact comparison unavailable, or changed dependencies/native artifacts with same publisher/source and no install/runtime privilege change.
- `BLOCK`: signature/checksum mismatch, CI artifact raw binary hash differs from release asset hash, publisher/Team ID/source URL changed, new or changed install/updater script, new obfuscated logic, unexplained network install path, credential/dotfile access, or untraceable artifact.

## Example
User: `OMP says: New version 15.10.4 is available. Run: omp update. Check before I install.`

Good response shape: compare installed OMP version to `15.10.4`; inspect what `omp update` would fetch without running it; compare release tag, package metadata, lockfile/dependencies, install scripts, tarball hashes, npm signatures/attestations; return `SAFE / CAUTION / BLOCK` with evidence. Do not audit unchanged OMP code.

## Common mistakes
| Mistake | Fix |
|---|---|
| Using `low risk` / `looks fine` | Use `SAFE / CAUTION / BLOCK`. |
| Giving a checklist only | Produce an evidence report with versions, hashes, and citations. |
| Running the update | Never execute updater/installer/candidate binary. |
| Full-auditing by default | Stay delta-scoped unless escalation criteria fire. |
| Ignoring provenance gaps | Mark `CAUTION` unless hashes/signatures/publisher/source trace are adequate. |
| Stopping at "no SLSA/cosign attestation" for GitHub releases | First try CI artifact byte comparison. If unavailable, correlate release logs, tag checkout, upload timestamps, uploader identity, and publish job before judging the provenance gap. |


## Rationalizations to reject
| Rationalization | Reality |
|---|---|
| "This is already trusted, so quick advice is enough." | Trusted current version does not prove the update artifact or updater path. |
| "No artifact available, but it looks normal." | Missing artifact/provenance evidence is at least `CAUTION`. |
| "The full audit skill is safer." | Full audit is only for unexplained high-risk delta surfaces. |
| "Running the updater would show what happens." | Pre-install audit forbids updater/installer/candidate execution. |
| "No SLSA means binary is unproven." | First try CI artifact byte comparison. If no artifact remains, inspect release logs for tag checkout, exact build/upload commands, release asset metadata, and publish job. This can reduce concern but remains `CAUTION` unless there is a byte match/signature/attestation. |

## Red flags
- Changed updater or install path.
- New lifecycle/postinstall script.
- New native binary or helper tool.
- Publisher, Team ID, bundle ID, registry, or source URL changed.
- Missing or mismatched checksum/signature/notarization.
- New permission, entitlement, daemon, login item, local service, or hidden network endpoint.
