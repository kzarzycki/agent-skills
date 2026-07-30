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
- derives one total order with an exact UTF-8 title tie-break and canonical
  blocker ordering;
- reconciles every marker before showing the exact remaining write plan;
- asks “Create these GitHub Issues now?” immediately before the first mutating
  `gh` call;
- limits approval to the displayed batch;
- stores the exact approval, marked issues, resolved URLs, and relationship
  progress in an atomically replaced state file;
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
invocation, persists issue and relationship state, and can lose a successful
creation response.
The scenarios prove:

- pending approval performs marker reads and no mutating `gh` command;
- rejection creates zero issues;
- approval creates issues in a deterministic total order with reviewed labels,
  stable markers, and immediate URL output;
- exact-batch approval and confirmed URLs survive a fresh process;
- a successful create with a lost response is recovered by marker without a
  duplicate;
- equivalent input permutations produce one hash and marker set;
- changed canonical batches require new approval;
- duplicate markers stop before approval or mutation; and
- the persisted and remote blocker graphs match.

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

## Fix Round 1

The review findings were verified against `4ee2361`. Approval, issue URLs, and
relationship progress existed only in one function call; the failure fixture
stopped before a remote write; sibling and blocker order followed input order;
approval preceded marker reads; and duplicate, changed-batch, and relationship
state branches were not exercised.

The tracker protocol now stores durable state at
`.scratch/agent-skills/github-issue-batches/{batch_sha256}.json`. Each transition
uses a sibling temporary file, file `fsync`, atomic replacement, and parent
directory `fsync`. Exact-batch resume loads the saved approval, reconciles all
markers, persists recovered URLs, creates only missing issues, and replays
pending relationship additions idempotently. Changed fingerprints start a new
preview and approval flow.

Fix-round TDD evidence:

- RED: 11 focused scenarios failed because the generated tracker declared
  fixture protocol version 1 and had no durable state contract.
- GREEN: the focused workflow, setup, and contract run passed 21 tests.

Fix-round final verification:

- `mise run test`: 77 tests passed; Ruff lint passed; 31 files passed format
  checking.
- `mise run vendor-engineering-check`: locked reproduction passed; 21 package
  tests passed; patch failures were none; changed skills were none.
- `git diff --check`: passed.

The deterministic fake remains the test boundary. No live GitHub command or
live-agent session ran.
