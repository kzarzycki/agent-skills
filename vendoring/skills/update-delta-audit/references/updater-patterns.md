# Updater patterns

Use these as targeted checks. Do not expand to a whole-product audit unless `SKILL.md` escalation criteria fire.

## CLI and package-manager updates
Capture:
- installed version and candidate version
- package manager/channel (`npm`, `pnpm`, `bun`, `pip`, `cargo`, `brew`, vendor CLI)
- lockfile or registry metadata before/after
- exact updater command, but do not run it

Check delta:
- package name, registry/source URL, publisher/maintainer
- integrity/checksum/signature/provenance metadata
- lifecycle scripts: `preinstall`, `install`, `postinstall`, `prepare`
- `bin`, `main`, `exports`, `files`, `os`, `cpu`
- dependency additions/removals/version jumps
- native build/download tools: `node-gyp`, `prebuild-install`, `curl`, `wget`, shell scripts, chmod

Verdict bias:
- new lifecycle script or registry/source change -> `BLOCK`
- new dependency/native binary with same publisher/source, valid integrity, and no install/runtime privilege change -> `CAUTION`
- version/hash-only delta plus valid provenance -> `SAFE`

## OMP example
For `New version 15.10.4 is available. Run: omp update`:
- identify current OMP package/binary and update channel
- inspect `omp update` implementation or package manager path without running it
- compare current tag/package to `15.10.4`
- fetch npm/GitHub artifacts read-only
- record tarball SHA-256, integrity, npm signature/attestation, workflow/commit provenance
- if updater uses GitHub binary fallback, compare the release binary bytes to the matching `omp-binary-<platform>` CI artifact from the successful release workflow run for the tag commit
- inspect install hooks and internal `@oh-my-pi/*` dependency delta
- mark `CAUTION` for any internal package lacking candidate provenance even if source diff is small

## GitHub releases
Check:
- current/candidate tags and compare URL
- release assets, checksums, signatures, attestations
- publisher identity and CI workflow that built assets
- changed release workflows/scripts since current version
- asset name/platform consistency

For binary release assets, perform practical CI provenance when the user trusts GitHub Actions:
1. Resolve the release tag to its commit SHA.
2. Find the GitHub Actions release workflow run for the tag/commit. Prefer a successful run whose build job checks out the release tag; if the workflow's controlling commit differs from the tag commit, verify the build job itself checks out `refs/tags/<tag>`.
3. Confirm the run detected/built the candidate release tag, not an unrelated branch build.
4. First preference: find the release-binary job and matching uploaded CI artifact for the platform. Download the CI artifact zip, verify its zip SHA-256 equals GitHub Actions artifact metadata/log digest, hash the contained raw binary bytes, hash the GitHub release asset, and compare byte-for-byte. Exact match establishes practical CI provenance; mismatch is `BLOCK`.
5. If no CI artifact is available, inspect the public build/publish logs before calling correspondence unproven:
   - checkout line for `refs/tags/<tag>` and resulting commit SHA
   - build command and publish command (`electron-builder --publish`, package manager publish, upload-release-asset, etc.)
   - log line naming the exact artifact path/name built
   - log line uploading that exact artifact name to the release provider
   - release asset metadata: uploader identity, created/updated timestamps, size, digest
   - publish/un-draft job logs showing the release stayed draft until required assets were verified
6. Correlate timestamps: the release asset creation time should align with the upload log line and uploader should be the expected CI identity. Treat this as corroborating provenance only; without byte comparison/signature/attestation, verdict remains `CAUTION` unless other checks justify `BLOCK`.

If binary assets are present without signatures/checksums/attestations and neither CI artifact comparison nor log/metadata correlation can be performed, use `CAUTION`; if asset source or publisher changed unexpectedly, use `BLOCK`.

## Homebrew formulae/casks
Check:
- formula/cask diff between current and candidate
- `url`, `sha256`, `version`, `depends_on`, `postflight`, `uninstall`, `zap`, `caveats`
- app bundle ID and Team ID for casks when available

Changed `postflight`/install scripts or URL host -> `BLOCK`.

## macOS apps: Sparkle/appcast/vendor feeds
Capture current app metadata first:
- `CFBundleIdentifier`, `CFBundleShortVersionString`, `CFBundleVersion`
- code signing Team ID, notarization status, entitlements
- update feed URL if visible in `Info.plist`, app resources, or network prompt

Candidate checks:
- feed/appcast entry contains the candidate version
- artifact URL is HTTPS and on the same vendor/GitHub/Homebrew domain already used by the current updater
- Sparkle `edSignature` or equivalent signature exists when the updater supports it
- downloaded DMG/ZIP/app SHA-256 recorded
- mounted/extracted bundle signing Team ID and bundle ID match current app
- notarization and hardened runtime are present when present on current app or required by the vendor's supported macOS channel
- entitlements/privacy usage strings do not add camera/mic/screen/accessibility/full-disk/network-server privileges unless the release notes and signed entitlement diff both account for them; otherwise use `BLOCK`

Use `scripts/macos-app-provenance.sh /Applications/App.app` on macOS for installed/candidate `.app` metadata. It inspects metadata only.

## Orca/StablyAI example
For an Orca StablyAI macOS update prompt:
- confirm the exact candidate version maps to an official update feed, release, cask, or vendor download
- compare current `/Applications/Orca.app` metadata against candidate bundle metadata
- require matching bundle ID and Team ID
- record notarization/spctl result and entitlements for both versions
- diff new domains/endpoints in app resources only if artifact is available
- if version `Xyz` cannot be mapped to an official feed/artifact, return `BLOCK` or `CAUTION` with "do not click yet" recommendation

## Generic vendor feeds
Check:
- HTTPS feed URL and artifact URL
- feed signing if documented
- candidate version exactly matches prompt
- artifact hash/signature if vendor publishes one
- publisher identity did not change

No public provenance is usually `CAUTION`, not `SAFE`.
