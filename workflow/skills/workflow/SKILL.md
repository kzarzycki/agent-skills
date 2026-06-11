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
   `<work-item dir>/01-DECISION-SPEC.md`. Runtime extras (interview form, notes) go under
   `<work-item dir>/_phases/spec/`. Derive research buckets from the prompt (codebase
   precedents, existing docs, external prior art -- whatever the prompt suggests) and gate
   (AskUserQuestion): the user approves, narrows, or rejects each bucket. Run only approved
   buckets.
2. Research. Call `Workflow({ name: 'research-brief', args: { prompt, buckets } })` with the
   approved buckets. Keep the returned `{ brief, openThreads }` and write both to
   `<work-item dir>/_phases/spec/research-brief.md`.
3. Interview + converge. The interview grills the user one question at a time, so it needs a live
   channel to them. A spawned teammate only gets that channel inside tmux. Detect with
   `[ -n "$TMUX" ]`, tell the user which mode applies and its cost, and ask them to accept
   (AskUserQuestion) before you start.

   - In tmux -- spawn the interviewer; it owns the whole phase: interview in its own pane, write
     the draft to `spec_path`, run this plugin's `spec-phase` saved workflow (format gate -> intent
     + testability reviewers -> rework, capped), relay any `needs-user` question to the user
     itself, and SendMessage you the artifact path + verdict summary when it passes. Compose the
     prompt yourself: work item, brief, open threads, `spec_path`, and `pluginRoot` inline --
     `spec_path` is what selects the interviewer's team file mode, `pluginRoot` is what it passes
     to the workflow:
     - `TeamCreate({ team_name: 'spec' })`
     - `Agent({ team_name: 'spec', name: 'interviewer', subagent_type: 'interviewer',
       prompt: "Work item: <prompt>\nResearch brief: <brief>\nOpen threads: <openThreads>\nspec_path: <spec_path>\npluginRoot: <plugin root>" })`
     A teammate's chat output never reaches you, so do not expect a return value. Wait for its
     message: path + verdicts (+ HTML gate page path if rendered). Do not Read the artifact.
   - Not in tmux -- run the interview yourself. Load the spec skill and follow its contract;
     the interview shares your context -- that is the cost the user accepted by choosing this
     mode. Lead with the open threads, resolve what you can from the codebase, write the draft to
     `spec_path`, then run the same loop: the `spec-phase` saved workflow (args/returns in its
     meta; `scriptPath: <plugin root>/workflows/spec-phase.js` fallback if the name is not in
     the session registry). On `needs-user` or `rework-cap-exceeded`, ask the user and re-run
     with their answer as `instructions`.

4. Present. Hand the user the gate per Gate presentation below. To approve, continue. To rework,
   message the interviewer if you spawned one (it re-runs the loop and re-signals) or re-run the
   `spec-phase` workflow yourself with the user's feedback as `instructions` -- then present again.
5. Close. If you spawned a team, shut down the interviewer (`SendMessage` with
   `{type: 'shutdown_request'}`), then `TeamDelete()`.

## Tech Options phase

Runs after the user approves the Decision Spec. You stay orchestrator -- never author or review
the artifact in your own context.

1. Delegate. Run this plugin's `tech-options-phase` saved workflow (args/returns in its meta;
   `pluginRoot` = the plugin root from Path resolution above; `scriptPath:
   <plugin root>/workflows/tech-options-phase.js` fallback if the name is not in the session
   registry). It runs the autonomous loop from the tech-options skill contract (analyst ->
   format gate -> two independent reviewers -> rework, capped). Pass `instructions` for user
   rework feedback and `contentFrozen: true` for shape-only rework. Without the Workflow tool,
   fall back per the tech-options skill's Execution section.
2. Present. On `status: pass`, hand the user the gate per Gate presentation below. On
   `needs-user` or `rework-cap-exceeded`, surface the reviewers' findings and ask the user to
   decide. Rework requested by the user = re-run step 1 with their feedback as `instructions`.
3. Stop. After the user approves Tech Options the engine stops -- planning is not implemented
   yet. Tell the user the work-item dir and artifact paths.

## Gate presentation

Every user gate, any phase: hand the user the artifact path plus a verdict/finding summary --
and the HTML gate page path when the phase workflow rendered one (`gatePage` in its return,
under `_phases/<phase>/`). The artifact content never enters your context; the user reviews
the file (or the HTML page) directly.

The HTML page is rendered inside the phase workflows, best-effort, via the
`experimental:communicating-in-html` skill. If the user pastes the page's copy-back token,
parse it as the gate answer. The markdown artifact stays the source of truth; without that
skill the gate is path + summary.
