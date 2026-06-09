# Baseline results

## Scenarios
Source: `pressure-scenarios.json`.

## Observed baseline behavior

### OMP update prompt
Baseline performed a useful real delta check: npm latest lookup, GitHub tag comparison, npm tarball metadata, install-script absence, npm/SLSA provenance, and internal package caveat. Remaining gaps for the skill to standardize:
- Verdict was `low-risk`, not the required `SAFE / CAUTION / BLOCK` vocabulary.
- Report shape was ad hoc.
- No reusable procedure for discovering updater mechanism before fetching artifacts.
- No explicit scope rule saying when to stop vs escalate.

### Orca/StablyAI macOS app prompt
Baseline stayed mostly checklist-level because candidate version `Xyz` could not be mapped to a public release. Useful caution, but gaps:
- No exact artifact/evidence template.
- No concrete macOS provenance command sequence.
- No clear `SAFE / CAUTION / BLOCK` classification.
- Did not distinguish Sparkle/appcast vs Electron/Squirrel vs vendor feed in enough detail for repeat use.

### Package-manager lockfile delta
Baseline produced good decision rules, but gaps:
- No exact artifact/evidence template.
- No command/checklist routing by package ecosystem.
- No provenance/hash capture requirement.
- No reusable escalation trigger to full audit.

## Failure patterns to address in the skill
- Agents may use non-standard verdict labels.
- Agents may produce advice/checklists instead of evidence-backed report sections.
- Agents may skip updater-mechanism discovery or treat it as implicit.
- Agents may omit artifact hashes/provenance when no concrete artifact is available yet.
- Agents may not know when to stop delta scope or escalate to full audit.
