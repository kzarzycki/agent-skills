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

## What each cannot do

- subagents/Workflow: no non-Claude agent, not interactive/persistent, no human cockpit.
- Herdr: Claude output read-back is scrape-only (use file handoff); single-host (SSH reattach), no cross-machine mesh, no cloud/web; no agent-lifecycle push (only raw terminal-stream via `terminal session observe`).
- SendMessage: Claude-only; can't spawn or place; can't force output from an uncooperative session; no blocked/approval detection.

Push and cross-machine/cloud are where Claude-native leads and Herdr is not architecturally headed -- don't wait on a Herdr roadmap for them.
