---
name: workflow
description: Use when the user wants to run a work item through the workflow engine, e.g. "/workflow <prompt>", "start a workflow for ...", or "run the workflow engine on ...".
---

# Workflow Engine

You are the workflow engine. You sequence the phases, delegate each one to a filter or an
agent, and present the result. The heavy work runs in the delegatees; you hold only the
prompt, the returned brief, and the returned spec, so your context stays small.

Input: a work-item prompt.

## Discuss phase

1. Research. Call `Workflow({ name: 'research-brief', args: { prompt } })`. Keep the returned
   `{ brief, openThreads }`.
2. Interview. The interview grills the user one question at a time, so it needs a live channel to
   them. A spawned teammate only gets that channel inside tmux. Detect with `[ -n "$TMUX" ]`, tell
   the user which mode applies and its cost, and ask them to accept (AskUserQuestion) before you
   start. Either way, create the work-item dir `.workflow/<yyyy-mm-dd>-<slug>/` with the layout
   from this plugin's `../../contracts/work-item.json` (relative to this skill's base dir);
   `spec_path` = `<work-item dir>/01-DECISION-SPEC.md`. Runtime extras (interview form, notes) go
   under `<work-item dir>/_phases/discuss/`.

   - In tmux -- spawn the interviewer; it grills in its own pane and your context stays small. Pass
     it the prompt, brief, open threads, and the `spec_path`:
     - `TeamCreate({ team_name: 'discuss' })`
     - `Agent({ team_name: 'discuss', name: 'interviewer', subagent_type: 'interviewer', prompt })`
     It writes the spec to `spec_path` and SendMessages you the path. You receive the spec only via
     that message plus the file -- a teammate's chat output never reaches you, so do not expect a
     return value. Wait for the message, then Read `spec_path`.
   - Not in tmux -- run the interview yourself. Load the discuss skill and follow its contract
     (interview composition, spec shape, format gate apply in-situ too). Lead with the open
     threads, resolve what you can from the codebase, then write the spec to `spec_path`. The
     interview shares your context -- that is the cost the user accepted by choosing this mode.

3. Present. First the format gate: `mdsmith check -c ../../contracts/mdsmith.yml <spec_path>`
   (relative to this skill's base dir). Send MDS020 findings back to the author for a fix before
   the user sees the spec; skip the gate only if mdsmith is not installed. Then show the user the
   spec from `spec_path` verbatim. To approve, continue. To rework,
   message the interviewer if you spawned one (it rewrites the same file and re-signals) or revise
   the file yourself if you ran in-situ -- then re-read `spec_path` and present again.

   HTML enrichment (optional, zero-coupling): if the `communicating-in-html` skill is loaded in
   this session, also render the gate as one self-contained HTML page under `_phases/<phase>/` --
   the full artifact embedded for browsing, reviewer verdicts, approve/rework choices with a
   copy-back token -- surface or serve it, and parse the pasted token as the gate answer. The
   markdown artifact stays the source of truth; without that skill this step is chat-only and
   nothing changes.
4. Close. If you spawned a team, shut down the interviewer (`SendMessage` with
   `{type: 'shutdown_request'}`), then `TeamDelete()`.
