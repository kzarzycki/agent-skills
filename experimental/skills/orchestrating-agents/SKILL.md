---
name: orchestrating-agents
description: Choose how to spawn, message, and read back from multiple agents. Use when deciding between Herdr, Claude-native SendMessage/subagents, or plain tmux to run parallel workers, Wayfinder waves, or an independent/alternative-agent review.
---

# Orchestrating agents

Pick the mechanism by job. They are not interchangeable, and the best fleet setup composes two.

## Decision

- **Owned, Claude-only, you want the results** (fan-out, headless review, waves with no human grilling) -> **subagents / Workflow**. Structured returns, no scraping, deterministic. Can't do non-Claude or a live cockpit.
- **A human supervises, or agents are mixed kinds** (codex/gemini + claude), or you must spawn+place, catch approval prompts, watch panes -> **Herdr**. Only thing with real lifecycle detection (`idle/working/blocked/done`, `agent wait --until`).
- **Talk to Claude sessions that already exist anywhere** (other worktree, other machine, cloud/web) -> **SendMessage / ListAgents**. Only channel with push and cross-machine.
- **1-2 agents, lowest dependency** -> plain **tmux** works, but it is blind to agent state.

## Control plane + data plane (the real answer for a Claude fleet)

Herdr to **spawn/place/supervise**; SendMessage as the **wire between agents and back to you**. This dodges Herdr's worst weakness (reading Claude output) by not using `agent read` for the payload.

## Hard-won reliability rules

- **Reading back long output: use file handoff, never scraping.** Tell the agent to write its full result as markdown to a temp path and reply only with the path; read the file. Applies to Herdr and tmux alike. Biggest reliability lever.
- **Herdr `agent prompt --wait` false-negatives on Claude panes** (`agent_prompt_stalled`) -- Claude renders on the alt screen. The message still lands. Prompt, ignore the error, then `agent read` / wait on the file. More trustworthy on non-Claude kinds.
- **Herdr `agent read` cannot recover alt-screen scrollback** -- short answers scrape fine, a long review does not. File handoff fixes it.
- **SendMessage read-back is structured and scrape-free** -- but Claude-only, and the target must *choose* to `SendMessage` back (instruct it: reply with your SendMessage tool, `to` = the `from` value). Permissions are per-session; no laundering.

## Spawning a fleet from Herdr (pattern that works)

- One tab per worker: `herdr tab create --workspace $HERDR_WORKSPACE_ID --cwd "$PWD" --label <slug> --no-focus`, read `.result.root_pane.pane_id`, wait ~3 s for the shell prompt, then `herdr agent start <slug> --kind claude --pane <id>`. `agent_pane_busy` right after `tab create` means the shell has not reached its prompt yet -- retry, do not recreate.
- Briefs go in files, prompts stay one line: write each brief to a scratch `.md` (task, scope, constraints, ground rules) and prompt `Read the brief at <path> and execute it end to end.` Long text through the pane is fragile; a path is not.
- Tell workers when to stop and ask: "AskUserQuestion only at a fork that changes what gets built or before anything hard to undo; the owner will visit your pane." Herdr then reports the pane as `blocked`.
- Coordinating concurrent workers on one repo: each in its own sibling worktree; when master moves under a long-running worker, `herdr agent prompt <name> "<one-line note>"` -- Claude queues typed input while working, so a nudge lands without waiting for idle.

## Knowing when a worker is really done

Herdr's `agent_status` classifies the **main prompt box only**. A Claude session whose main loop is idle while Task/Agent subagents, a background Bash, or a Monitor still run reads as `idle`/`done`. The only place those show is the rendered pane, so poll `agent read --source visible` and treat the session as busy while any of these is present:

- a running-subagent row under `⏺ main`: `◯ Explore  Grepping docs…  54s · ↓ 64.5k tokens`
- the turn spinner: `✶ Zigzagging… (4m 57s · ↓ 15.6k tokens)`
- the status-line segment for background tasks: `· 1 shell, 1 monitor ·`
- a usage-limit pause: `⚠ Usage limit reached · continuing shortly` -- the session auto-resumes, so it is waiting, not done (every worker in a fleet hits this at the same minute)

Declare DONE only after two consecutive polls with none of them, plus herdr `idle`/`done`. `scripts/herdr_watch.sh <name> [poll_s]` implements this and emits one line per transition (WORKING/IDLE/DONE/BLOCKED/GONE) -- arm it with the Monitor tool (persistent) instead of sleeping in the main loop. Two traps it already avoids: run polls from `/tmp`, not a project dir (a broken `mise.toml` there kills the shimmed `python3` and an empty status looks like a vanished agent), and require three failed lookups before GONE.

## What each cannot do

- subagents/Workflow: no non-Claude agent, not interactive/persistent, no human cockpit.
- Herdr: Claude output read-back is scrape-only (use file handoff); single-host (SSH reattach), no cross-machine mesh, no cloud/web; no agent-lifecycle push (only raw terminal-stream via `terminal session observe`).
- SendMessage: Claude-only; can't spawn or place; can't force output from an uncooperative session; no blocked/approval detection.

Push and cross-machine/cloud are where Claude-native leads and Herdr is not architecturally headed -- don't wait on a Herdr roadmap for them.
