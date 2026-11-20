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

`land`'s batch gate runs the `Affected tests:` command (`check-fast`: the tests the batch's combined diff touches plus lint) against the tip the batch merges onto; `check-land`, the vendor check and lint without tests, is the `gate` line's full-mode command. The PR's `qualify` check runs the tests it touches and the nightly run covers the rest.

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
