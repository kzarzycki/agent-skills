# Agent orchestration gotchas

## Forks can relay `AskUserQuestion`; custom subagents and forks are mutually exclusive

`Agent({ subagent_type: 'fork' })` inherits the parent conversation **and** the parent's
tools — including `AskUserQuestion`. A fork spawned in the background can prompt the user
directly (one question at a time) with its Q&A staying out of the spawner's context. This is
the mechanism for an interactive interview that must not pollute an orchestrator's context.

`subagent_type` is a single slot, so you cannot have both at once:

- **`fork`** — inherits conversation + parent tools; ignores any custom agent definition
  (no custom system prompt / skill preloads). Load needed skills from inside the fork's prompt.
- **named custom agent** (e.g. `workflow:interviewer`) — fresh context, carries its own
  contract + tool grants, but starts blind to the conversation.

Pick fork when the delegate needs the conversation so far (prior brainstorming, briefs);
pick a named agent when it needs a specialized contract more than history.

**Trust the empirical test over doc-reading.** A `claude-code-guide` agent (reading current
docs) asserted `AskUserQuestion` is unavailable to *all* subagents including forks. A direct
spawn test proved forks relay fine. When a delegate's runtime capability is in question, spawn
one and check — don't take a docs summary as ground truth.
