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
   start. Pick a `spec_path` either way (e.g. `_decision-spec.md` in the working dir).

   - In tmux -- spawn the interviewer; it grills in its own pane and your context stays small. Pass
     it the prompt, brief, open threads, and the `spec_path`:
     - `TeamCreate({ team_name: 'discuss' })`
     - `Agent({ team_name: 'discuss', name: 'interviewer', subagent_type: 'interviewer', prompt })`
     It writes the spec to `spec_path` and SendMessages you the path. You receive the spec only via
     that message plus the file -- a teammate's chat output never reaches you, so do not expect a
     return value. Wait for the message, then Read `spec_path`.
   - Not in tmux -- run the interview yourself, following this plugin's `agents/interviewer.md`: run
     `mattpocock-skills:grill-me` leading with the open threads, resolve what you can from the
     codebase, then write the spec to `spec_path`. The interview shares your context -- that is the
     cost the user accepted by choosing this mode.

3. Present. Show the user the spec from `spec_path` verbatim. To approve, continue. To rework,
   message the interviewer if you spawned one (it rewrites the same file and re-signals) or revise
   the file yourself if you ran in-situ -- then re-read `spec_path` and present again.
4. Close. If you spawned a team, shut down the interviewer (`SendMessage` with
   `{type: 'shutdown_request'}`), then `TeamDelete()`.
