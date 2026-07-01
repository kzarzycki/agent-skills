---
name: workflow
description: Use when the user wants to run a work item through the workflow engine, e.g. "/workflow <prompt>", "start a workflow for ...", or "run the workflow engine on ...".
---

# Workflow Engine

You are the workflow engine. You sequence the phases, delegate each one to a filter or an
agent, and present the result. The heavy work runs in the delegatees; you hold only the
prompt, the returned brief, and artifact paths plus verdicts, so your context stays small.

Input: a work-item prompt.

Path resolution: the plugin root is the directory containing this skill's `contracts/`
sibling (`${CLAUDE_PLUGIN_ROOT}` when set). All `../../contracts/...` paths in this file
resolve from this skill's base dir inside that root. Work-item paths (`.workflow/...`)
resolve from the project root.

This engine is stateless -- chat history is the state; to resume, re-read the work-item dir.

## Spec phase

1. Propose research. Create the work-item dir `.workflow/<yyyy-mm-dd>-<slug>/` with the
   layout from this plugin's `../../contracts/work-item.json`; `spec_path` =
   `<work-item dir>/01-DECISION-SPEC.mdx`. Runtime extras (interview form, notes) go under
   `<work-item dir>/_phases/spec/`. Derive research buckets from the prompt (codebase
   precedents, existing docs, external prior art -- whatever the prompt suggests) and gate
   (AskUserQuestion): the user approves, narrows, or rejects each bucket. Run only approved
   buckets. Capture any constraint the user adds at this gate verbatim and bake it into the
   research prompt and the interview.
2. Research. Call `Workflow({ name: 'research-brief', args: { prompt, buckets } })` with the
   approved buckets. Keep the returned `{ brief, openThreads }` and write both to
   `<work-item dir>/_phases/spec/research-brief.md`.
3. Interview + converge. By default the engine delegates the interview to a **fork** of itself
   (`Agent({ subagent_type: 'fork' })`). A fork is the one delegate that can run the interview:
   it inherits the whole conversation so far -- the research brief, the open threads, the
   brainstorming already done -- and inherits this agent's tools, including `AskUserQuestion`, so
   it prompts the user one question at a time in the background while its Q&A stays out of the
   engine's context. (A fresh `interviewer` agent only has `AskUserQuestion` because its
   definition grants it, and starts blind to the conversation -- the fork beats it on both
   counts.) The fork owns the whole phase: interview, write the draft to `spec_path`, run this
   plugin's `spec-phase` saved workflow (format gate -> intent + testability reviewers -> rework,
   capped), relay any `needs-user` to the user itself, and SendMessage you the artifact path +
   verdict summary when it passes.
   - `Agent({ subagent_type: 'fork', name: 'interviewer',
     prompt: "You are the spec interviewer. You have the full conversation context, including the
     research brief and open threads. Load the spec contract (Skill workflow:spec) and its
     interview skills (superpowers:brainstorming, mattpocock-skills:grill-me) -- a fork does not
     pick up the interviewer agent definition, so load them yourself. Lead with the open threads,
     resolve what you can from the codebase, write the draft to <spec_path>, then run spec-phase
     with pluginRoot <plugin root>. Relay needs-user to the user; SendMessage me the path +
     verdicts when it passes." })`
   A fork's tool output never reaches you, so do not expect a return value. Wait for its message:
   path + verdicts. Do not Read the artifact.

   In-situ on request -- only when the user asks for it (an `in-situ`/`inline` cue in the prompt
   or `--inline`): run the interview yourself instead of delegating. Load the spec skill and
   follow its contract; the interview shares your context -- the cost the user opted into. Lead
   with the open threads, resolve what you can from the codebase, write the draft to `spec_path`,
   then run the same `spec-phase` loop (args/returns in its meta; `scriptPath: <plugin
   root>/workflows/spec-phase.js` fallback if the name is not in the session registry). On
   `needs-user` or `rework-cap-exceeded`, ask the user and re-run with their answer as
   `instructions`.

4. Present. Hand the user the gate per Gate presentation below. To approve, continue. To rework,
   message the interviewer if you spawned one (it re-runs the loop and re-signals) or re-run the
   `spec-phase` workflow yourself with the user's feedback as `instructions` -- then present again.
5. Close. If the interviewer fork is still alive after approval, shut it down (`SendMessage` with
   `{type: 'shutdown_request'}`). The fork path uses no team, so there is nothing to `TeamDelete`.

## Tech Design phase

Runs after the user approves the Decision Spec. You stay orchestrator -- never author or review
the artifact in your own context.

1. Delegate. Run this plugin's `tech-design-phase` saved workflow (args/returns in its meta;
   `pluginRoot` = the plugin root from Path resolution above; `scriptPath:
   <plugin root>/workflows/tech-design-phase.js` fallback if the name is not in the session
   registry). It runs the autonomous loop from the tech-design skill contract (designer ->
   format gate -> two independent reviewers -> rework, capped). Pass `instructions` for user
   rework feedback and `contentFrozen: true` for shape-only rework. Without the Workflow tool,
   fall back per the tech-design skill's Execution section.
2. Present. On `status: pass`, hand the user the gate per Gate presentation below. On
   `needs-user` or `rework-cap-exceeded`, surface the reviewers' findings and ask the user to
   decide. Rework requested by the user = re-run step 1 with their feedback as `instructions`.
3. Stop. After the user approves the Tech Design the engine stops -- planning is not implemented
   yet. Tell the user the work-item dir and artifact paths.

## Gate presentation

Every user gate, any phase: a chat summary (verdicts + findings + artifact path) plus a live
decision page. The artifact content never enters your context; the user reviews the served
page, and the markdown stays the source of truth.

MDX rendering. Both the Decision Spec and the Tech Design are MDX authored with
communicating-in-mdx components (see the spec and tech-design skills): render and serve them
through that skill's runner — `<DocInclude>` the current `01-DECISION-SPEC.mdx` /
`02-TECH-DESIGN.mdx` so its diagrams and callouts render, demote the changelog and a
`<DocDiff>` of rework rounds below a `---`, and take the decision with a `<QuestionForm>`. Any
non-MDX artifact uses the communicating-in-html protocol below; either way the answer mapping
is the same.

The communicating-in-html mechanics are its "Live decision pages" protocol (render →
serve → state file → watcher → process); its two assets live in that skill's `assets/` dir
(in this repo: `<repo root>/experimental/skills/communicating-in-html/assets/`). Workflow
bindings on top of that protocol:

- Render (deterministic, zero tokens -- phase workflows do not render):
  `python3 <assets>/render-decision-page.py --artifact <artifact> --gate <phase>
  --contract <plugin root>/contracts/<phase-contract>.json
  --verdicts '<verdicts JSON from the workflow return>' --out <work-item dir>/_phases/<phase>/gate.html`
  The contract's `display` map upgrades named sections to widgets (e.g. Tech Design's Scorecard
  -> sticky sentiment matrix); unhinted sections stay annotatable prose. On re-renders after
  rework, pass `--banner "Reworked from your gate answer (round N) -- <what changed>"`.
- Serve with `<assets>/gate-server.py --dir <work-item dir>`; channel files at
  `<work-item dir>/_gate/` (state.json, answers/). One server and one channel per work item,
  reused across every phase gate; stop the server when the engine stops.
- Arm the answer watcher whenever a gate is open; re-arm on fire or expiry.
- Answer mapping: `decision: approve` -> record approval, continue the engine.
  `decision: rework` -> re-run the phase workflow with `instructions` built from `feedback`
  plus the `annotations` (each `{target, comment}` is an instruction scoped to that artifact
  section); then re-render, bump `version`, set `idle`, re-present. A workflow `needs-user`
  while the page is open -> set state `needs-console` with the question summary, ask in chat,
  and bump `version` after resolving.
- A pasted `ANSWERS<<<…>>>ANSWERS` token is the same answer arriving by chat -- process
  identically. Without a browser the gate is path + summary.
