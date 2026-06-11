---
name: workflow
description: Use when the user wants to run a work item through the workflow engine, e.g. "/workflow <prompt>", "start a workflow for ...", or "run the workflow engine on ...".
---

# Workflow Engine

You are the workflow engine. You sequence the phases, delegate each one to a filter or an
agent, and present the result. The heavy work runs in the delegatees; you hold only the
prompt, the returned brief, and the returned spec, so your context stays small.

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
3. Interview. The interview grills the user one question at a time, so it needs a live channel to
   them. A spawned teammate only gets that channel inside tmux. Detect with `[ -n "$TMUX" ]`, tell
   the user which mode applies and its cost, and ask them to accept (AskUserQuestion) before you
   start.

   - In tmux -- spawn the interviewer; it grills in its own pane and your context stays small.
     Compose the prompt yourself: work item, brief, open threads, and `spec_path` inline --
     `spec_path` is what selects the interviewer's file mode; a bare prompt selects schema return
     mode, whose chat output never reaches you:
     - `TeamCreate({ team_name: 'spec' })`
     - `Agent({ team_name: 'spec', name: 'interviewer', subagent_type: 'interviewer',
       prompt: "Work item: <prompt>\nResearch brief: <brief>\nOpen threads: <openThreads>\nspec_path: <spec_path>" })`
     It writes the spec to `spec_path` and SendMessages you the path. You receive the spec only via
     that message plus the file -- a teammate's chat output never reaches you, so do not expect a
     return value. Wait for the message, then Read `spec_path`.
   - Not in tmux -- run the interview yourself. Load the spec skill and follow its contract
     (interview composition, spec shape, format gate apply in-situ too). Lead with the open
     threads, resolve what you can from the codebase, then write the spec to `spec_path`. The
     interview shares your context -- that is the cost the user accepted by choosing this mode.

4. Format gate. `mdsmith check -c ../../contracts/mdsmith.yml <spec_path>`. MDS020 = contract
   violation -- the author must fix it before the user sees the artifact. MDS023/MDS036/MDS056 =
   language budget -- pass to the author as rework input, not blockers. Without mdsmith
   installed, verify sections manually against the contract JSON.
5. Review gate. Spawn both reviewers in parallel (one message, two Agent calls):
   `subagent_type: 'workflow:intent-reviewer'` and `subagent_type: 'workflow:testability-reviewer'`.
   Each gets `spec_path`, writes evidence to `<work-item dir>/_reviews/spec/<reviewer>.md`,
   and returns a verdict: `pass`, `needs-rework`, or `needs-user`. On needs-rework, route the
   findings back to the author (message the interviewer if spawned, else rework in-situ) and
   re-run steps 4-5; cap 2 rework rounds, then escalate to the user. On needs-user, surface the
   findings and ask the user to decide.
6. Present. Show the user the spec from `spec_path` verbatim. To approve, continue. To rework,
   message the interviewer if you spawned one (it rewrites the same file and re-signals) or revise
   the file yourself if you ran in-situ -- then re-run steps 4-5, re-read `spec_path`, and present
   again.
7. Close. If you spawned a team, shut down the interviewer (`SendMessage` with
   `{type: 'shutdown_request'}`), then `TeamDelete()`.

## Tech Options phase

Runs after the user approves the Decision Spec. You stay orchestrator -- never author or review
the artifact in your own context.

1. Delegate. Run this plugin's saved workflow:
   `Workflow({ name: 'tech-options-phase', args: { workId, pluginRoot, instructions?, contentFrozen? } })`
   (`pluginRoot` = the plugin root from Path resolution above; if the name is not registered in
   this session, pass `scriptPath: <plugin root>/workflows/tech-options-phase.js` instead).
   It runs the autonomous loop from the tech-options skill contract (analyst -> format gate ->
   two independent reviewers -> rework, capped) and returns
   `{ status, rounds, verdicts, formatGate, artifact }`. Pass `instructions` for user rework
   feedback and `contentFrozen: true` for shape-only rework. Without the Workflow tool, fall
   back per the tech-options skill's Execution section.
2. Present. On `status: pass`, show the user `02-TECH-OPTIONS.md` verbatim plus a one-line
   verdict summary. On `needs-user` or `rework-cap-exceeded`, surface the reviewers' findings
   and ask the user to decide. Rework requested by the user = re-run step 1 with their feedback
   as `instructions`.
3. Stop. After the user approves Tech Options the engine stops -- planning is not implemented
   yet. Tell the user the work-item dir and artifact paths.

## Gate presentation

Every user gate, any phase: show the artifact verbatim in chat.

HTML enrichment (optional, zero-coupling): if the `communicating-in-html` skill is loaded in
this session, also render the gate as one self-contained HTML page under `_phases/<phase>/` --
the full artifact embedded for browsing, reviewer verdicts, approve/rework choices with a
copy-back token -- surface or serve it, and parse the pasted token as the gate answer. The
markdown artifact stays the source of truth; without that skill the gate is chat-only and
nothing changes.
