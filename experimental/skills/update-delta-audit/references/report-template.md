# Report template

Use this exact shape. Keep findings tied to observed evidence.

```markdown
## Verdict: SAFE | CAUTION | BLOCK
One-sentence reason.

## Compared
- Software:
- Current version:
- Candidate version:
- OS/channel:
- Audit directory:

## Update mechanism
- Prompt/command:
- Updater type:
- What it would fetch:
- What was not executed:

## Delta reviewed
- Release/source delta:
- Manifest/lockfile/dependency delta:
- Installer/updater script delta:
- Binary/artifact delta:
- Permission/entitlement delta:
- Network/update endpoint delta:

## Findings
- **Finding name.** Evidence (`path`, URL, hash, signature metadata, or command output). Impact.

## Provenance checks
- Artifact hashes:
- Signatures/checksums:
- Publisher/Team ID/registry identity:
- Source tag/build/attestation:
- CI artifact comparison, if GitHub binary:
  - tag commit:
  - workflow run:
  - CI artifact zip digest:
  - contained binary hash:
  - release asset hash:
  - release-log correlation when CI artifact is unavailable:
    - checked-out tag/commit:
    - build/upload log lines:
    - asset uploader/timestamps:
    - publish/un-draft verification:
- Gaps:

## Recommendation
Install / do not install / ask vendor for missing provenance. Include exact next command only when safe.
```

Rules:
- If no findings affect the verdict, write `None.` under Findings.
- If an artifact is unavailable, say so and classify the gap.
- Do not use `low risk`, `probably safe`, or `OK`; use `SAFE / CAUTION / BLOCK`.
- Do not claim cryptographic GitHub release binary/source correspondence unless provenance, attestation, reproducible build data, or byte-for-byte CI artifact comparison supports it. Log/metadata correlation is useful evidence but remains a provenance gap.
