# Loop facts

The engineering loop's values for this repo. `engineering/skills/engineering-loop/SKILL.md`
(Approvals and proof) defines what each line approves and what still waits for the owner.

Orchestration backend: omnigent

## Approvals

- spec: auto
- merge: auto unless risk

The owner's reason: specs and merges are approved by policy, so work doesn't stop on them.
No `risk:` rule is set; what still waits for the owner is what the loop builds in: a spec
opened by an account without write access, `risk:high` on a PR or issue, and the verifier's
cap reached with a blocker or major open.
