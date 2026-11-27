# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.8 - 2026-11-27

- `pin_update.py` follows a pin's own line: a `-next` pin moves to the newest newer tag of either line and never down to stable, a stable pin ignores `-next` tags, and every dependency pinned to a tag of the pack's repo moves by its own package prefix (#2772).

## 0.1.7 - 2026-11-26

- `pin_update.py` also runs `apm update` (transitive packages too) and `apm audit`, rolls back an install that removes a skill, and commits with a compare link per moved pin; hygiene's pack-lag check reads every package of a lock (#2706).
- `pin_update.py` also runs when only a sibling package has a newer release (#2706).

## 0.1.6 - 2026-11-26

- chief-of-staff: the pin updater reads the new release's `bump-from.yml` and, for a pin older than its `oldest`, refuses the jump and names the release to bump to and land first (#2709).

## 0.1.5 - 2026-11-26

- chief-of-staff: one values file, `cos-values.yml` in a setup's home folder, and `scripts/cos_values.py`, the loader every pack script imports: it checks each key, names an unknown or missing one, and gives a setup with no file the pack defaults (#2484).
- chief-of-staff: `cos_page.py` resolves the installed copy of `omnigent-agents`, never a developer checkout of the pack: a checkout (a git tree holding the marketplace file) is searched only where `AGENT_SKILLS_CHECKOUT` is set, as the pack's own tests set it (#2485).
- chief-of-staff: `scripts/decisions.py`, the decision log and morning digest: `log` appends a decision and refuses one with no undo line, `digest` drafts the morning digest from the log and the board's `## Needs the owner` and sends nothing, `sent` records the hand send; it reads `decisions.*` and `cos_session` through the values file (#2486).
- chief-of-staff: `scripts/start_gate.py`, the start gate: `check --repo --host` refuses a host the values file's `hosts.table` does not list for the repo, an `hosts.owner_requested_only` host the owner did not ask for, and a repo in a `managers` scope started outside its manager's registry; with no table it allows any host (#2487).
- chief-of-staff: `scripts/hygiene.py`, the nightly hygiene scan: it reports a board over 4 KB without rewriting it, archives a reaped lead's report after 14 days (never one a registry or state file still names), names `budget`, `parked` and `models.tiers` entries past their end date, any package behind the pack's latest release on each host, and a setup file that restates a pack sentence, and ends with the hosts and repos it did not reach; it reads `hygiene.repos` (the retention, board limit and authors are fixed) (#2488).
- chief-of-staff: `scripts/pin_update.py`, the pin updater: moves a consumer repo's pack pin to the newest `pin.tag_prefix` release tag, installs it and relays an `ACTION NEEDED:` line to `cos_session`; it skips on uncommitted edits to the lock or deployed files, rolls back a failed install, commits nothing and refuses the pack's own checkout (#2489).
- chief-of-staff: `roles/pm.md`, one project-manager role template for a tree of coordinators, with each hard limit and its reason; a project's scope, registry and board come from `managers` in the values file, its own limits from its node's instructions (#2490).
- chief-of-staff: the skill gains the generic rules both setups kept outside the pack: steward mode (replaces "an approval prompt stays the owner's"), a refusal is not a stop, cards only for the owner, card-first asking where a card tool exists, stopping and cleanup by verified id, ops go to hygiene, fall-back for an experimental agent kind, and a section for aligning with another setup on the issue or PR (#2491).
- chief-of-staff: the values loader drops the keys the owner's scope sweep removed (a values file that sets one fails as an unknown key), the sample files no longer set them, and the decision log names the CoS session from `cos_session` only (#2554).
- chief-of-staff: the pack's own CI finds its scripts in the checkout it runs in: a checkout counts when it is the `GITHUB_WORKSPACE` of the job running there, so main's push run, the nightly and the tag check run `nightly.py moved` again (#2560).
- chief-of-staff: the hygiene restate check also reads the board's `## Standing decisions` section, and a values file that sets no hosts no longer reports the local hostname as "not reached" (#2459).

## 0.1.4 - 2026-11-24

- chief-of-staff: the `USER NEEDED` row covers only a lead with no card open: a lead's own question goes back to it to ask on its card, and one that spans projects goes on the chief of staff's own card (#2170).
- chief-of-staff: a `card-waiting` event (a lead's card unanswered past 4 hours) is answered only under the owner's standing decision to act in their name; otherwise nothing is sent (#2170).
- chief-of-staff: Authority says a lead records an approval the owner gave on its own card, and a brief never tells a lead not to run `approve` (#2170).

## 0.1.3 - 2026-11-23

- `chief-of-staff`: owner-approval delegation is an optional mode the owner turns on and off on the root board, under which each project manager answers its own project's question cards and the chief of staff its own leads' and cross-project ones, through the card, logged with its undo, with the owner-only kinds left on the card and `loop.delegate_spec: false` as a project's opt-out; and a tree of coordinators (nodes, one writer per board, cards as the owner channel, asks down and reports up, the decision log) is described once in the skill, with the board's dated archive (#2044).

## 0.1.2 - 2026-11-22

- chief-of-staff: a lead takes one request or epic; a new, unrelated item goes to a fresh lead, never to one that is running or done (#1830).

## 0.1.1 - 2026-11-22

- chief-of-staff: the one-writer rule names a lead that merges, not rebases, in a shared checkout (#1768).

## 0.1.0 - 2026-11-22

- chief-of-staff: the first release, split out of `engineering`. It holds the `chief-of-staff` skill and, under `cos-console/`, the cos-console mod, still its own plugin so it stays enabled only in the chief of staff's home. It depends on `loop` and `omnigent`; `cos_page.py` finds `omnigent_agent.py` in the `omnigent-agents` skill wherever the host installed it (#615).
