# Task 5 Report: GitHub Issue Batch Publication

## Result

GitHub Issue publication now uses an approval-gated, interruption-safe batch
contract. The contract is owned by
`engineering/patches/mattpocock-skills/0002-github-issue-batch.patch`; the three
changed skill leaves remain generated from the pinned upstream source.

The generated GitHub tracker template now:

- renders every proposed issue with its title, complete body, labels, blockers,
  and dependency order;
- hashes canonical UTF-8 JSON containing those five fields;
- adds
  `<!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->`
  to each issue body;
- asks “Create these GitHub Issues now?” after review and before the first
  mutating `gh` call;
- limits approval to the displayed batch;
- searches every marker across all issue states before creation;
- reuses one exact match, stops on multiple matches, and creates only missing
  issues;
- prints each confirmed issue URL as soon as it is known; and
- wires child and blocking relationships after every issue URL exists.

`to-tickets` and `wayfinder` default real-tracker publication to GitHub Issues.
Both render the full batch before creation and delegate approval, creation,
resume, and relationship details to `docs/agents/issue-tracker.md`.

## Tests

`engineering/tests/test_github_issue_workflow.py` runs the declared tracker
protocol against `engineering/tests/fixtures/fake-gh`. The fake logs every
invocation, persists issue state, and can fail after two successful creations.
The scenarios prove:

- pending approval invokes no `gh` command;
- rejection creates zero issues;
- approval creates issues in dependency order with the reviewed labels,
  deterministic markers, and immediate URL output;
- relationships start after all three issue identities exist; and
- a retry after the third creation fails reuses issues one and two, creates only
  issue three, and leaves exactly three issues in state.

TDD evidence:

- RED: the four focused tests failed because the generated tracker template had
  no `github-issue-batch-fixture-protocol`.
- GREEN: the focused workflow and package contract run passed 7 tests.

Final verification:

- `mise run test`: 70 tests passed; Ruff lint passed; 31 files passed format
  checking.
- `mise run vendor-engineering-check`: locked reproduction passed; 14 package
  tests passed; patch failures were none; changed skills were none.
- `git diff --check`: passed.

## Reproduction

`engineering/patches/series` applies the setup-name patch followed by the GitHub
batch patch. `mise run vendor-engineering` regenerated the three skill outputs
and `engineering/provenance.yml` from upstream commit
`2ab958093e83e0ec752e6c1c5932da465bf23e0c`. The locked check reproduced the
same outputs and patch hashes.

## Concern

The deterministic fixture exercises the declared command boundary and resume
state without GitHub access. It does not run a live agent or call GitHub.
