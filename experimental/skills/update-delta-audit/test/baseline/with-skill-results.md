# With-skill results

## OMP update prompt
Output complied with the skill:
- Used `CAUTION` verdict.
- Identified updater mechanism: npm/Bun global update path vs GitHub binary fallback.
- Reported artifacts and SHA-256 values.
- Checked install scripts and npm/GitHub provenance.
- Stayed delta-scoped and did not run `omp update`.

## Orca/StablyAI macOS app prompt
Output complied with the skill:
- Used `BLOCK` because candidate `Xyz` did not map to an official observed release/feed artifact.
- Identified Electron updater/GitHub release feed uncertainty.
- Called out Team ID/notarization/entitlements/signing gaps.
- Did not install or run the update.

## Package-manager lockfile delta
Output complied with the skill:
- Used `CAUTION` because artifacts and lockfile were not provided.
- Stayed delta-scoped.
- Listed lockfile, dependency, install-script, provenance, and escalation checks.
- Avoided whole-package audit by default.

## Refactor observations
No new rationalization appeared in the with-skill runs. Add an explicit rationalization table anyway to lock in the baseline failures: generic verdict labels, checklist-only reports, running the updater, full-audit drift, and ignoring provenance gaps.
