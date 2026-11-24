# Loop facts

The engineering loop's values for this repo. `engineering/skills/engineering-loop/SKILL.md`
(Approvals and proof) defines what each setting approves and what still waits for the owner.

Orchestration backend: omnigent

Affected tests: mise run check-fast

Worker model: mid for size:S or smaller

A mid worker costs about half a top one per item, and a small item needs no more.

Verifier model: mid for not risk:high

Lead model: mid for size:S or smaller

A lead on a size:S item runs routine rounds, and a mid lead costs half a top one per token.

Lead autocompact: 200k

A lead re-reads its whole context every turn, so a smaller window costs less per turn; its notes
file carries the run's state across a compaction. Raise or remove the line if leads lose track.

## Approvals

Specs and merges are approved by policy, so work doesn't stop on them; the owner sees only
what no automated check can settle. A `risk:high` PR into a feature branch lands on the chief
of staff's `approved:merge` (`approvals.py delegate`), so dependent work doesn't stall; into
main the chief of staff's go is `approvals.py approve merge --by delegate` on the head (`delegate: all` in
gatekeeper.md).

`land` hands PRs to the Mergify merge queue (`land.queue: mergify` in gatekeeper.md, `.mergify.yml`): it posts the `land` status and adds `loop:queued` on each landable PR's head and exits, and Mergify tests each batch of up to 3 as a draft PR from `mergify/merge-queue/` into main, where `qualify` runs `test-batch`, the tests the batch's combined diff touches, retries a red batch once, splits a batch still red until only the failing PR leaves, and squash-merges the rest on green. A PR head's `qualify` runs only `check-fast` (vendor check, lint, the `.mergify.yml` template drift check), so each tree's tests run once, on its batch. A PR it drops gets `loop:dequeued`, and the next `land` turns it back to draft. No host runs a landing gate.

The `gate` line, `check-fast` (the vendor check, lint and the `.mergify.yml` drift check, no tests, since the tests run on the Mergify batch), is the command the worker's final-head `local-ci --record` runs and a PR head's `qualify` reads by tree; it is `land`'s batch gate only where it lands without a queue: with the Mergify queue set no landing runs it, and it stays the merge check `local-ci` runs. The nightly run covers the rest.

## Cloud worker

Cloud worker: claude-cloud, gate test, env agent-skills-dev

Cloud verifier: worker session, else codex thread

Workers run in an environment that holds one secret, so their compute leaves the owner's
machines: a ChatGPT access token for the verifier, which lasts up to 10 days and carries no
refresh token, so a session can run Codex but cannot renew or replace the login. The verifier
of a cloud worker's PR runs in that worker's kept session, on its checkout and build
(SKILL.md, Verifier in the worker's VM). Before starting a worker, run
`engineering/skills/engineering-loop/scripts/cloud_verifier.py seed`: it renews the stored
seed login when under 5 days are left, or uses the host's own Codex login (read only, never
refreshed or written) when its access token has at least a day left (`--host-min-days`),
puts the copy into the environment and allows the hosts
Codex needs there: `chatgpt.com`, `*.chatgpt.com`, `auth.openai.com` and `api.openai.com`.
When it says no login is usable, the owner logs in to Codex on the host, or runs its `login` once.

The live-agent suites (`test-engineering-agents`, `test-chief-of-staff-live`) need
logged-in harnesses and Omnigent, so they stay with the host lead. A cloud session clones the
pushed branch, so push before starting a worker. `.claude/claude-cloud-setup.sh` (the older `.claude/cloud-setup.sh` is still read) is the
environment's setup script; the environment keeps its own copy, so apply a change with
`POST /v1/environment_providers/<id>`, `config.init_script` set to the file.
