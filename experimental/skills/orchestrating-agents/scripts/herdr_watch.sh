#!/bin/zsh
# usage: herdr_watch.sh <agent-name> [poll_s]
# Emits one line per state transition; exits when the agent settles (done, no subagents) or vanishes / blocks.
# "busy" = herdr says working OR the rendered pane shows a spinner line or a running-subagent row
#   (herdr's agent_status only classifies the main prompt box; a running Task/Agent subagent
#   renders as "◯ Name  <desc>  12s · ↓ 3.1k tokens" under a "⏺ main" header while main sits idle).
cd /tmp  # never inherit a project cwd: a broken mise.toml there kills the shimmed python3
name=$1; poll=${2:-15}; prev=""; settled=0; miss=0
while true; do
  st=$(herdr agent get "$name" 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["agent"]["agent_status"])' 2>/dev/null)
  if [ -z "$st" ]; then miss=$((miss+1)); [ $miss -ge 3 ] && { echo "$name: GONE (3 consecutive lookups failed)"; exit 0; }; sleep $poll; continue; fi; miss=0
  pane=$(herdr agent read "$name" --source visible --lines 80 2>/dev/null)
  sub=$(printf '%s' "$pane" | grep -cE '^\s*[◯◐◑◒◓◔◕●] \S.*[0-9]+s · ↓' )
  spin=$(printf '%s' "$pane" | grep -cE '^[✢✳✶✻✽·⠂⠄⠆⠇⠧⠷⠿] [A-Z][a-z]+… \(' )
  # background shells/monitors show in the status line as '· 1 shell, 1 monitor ·'
  bg=$(printf '%s' "$pane" | grep -cE '· [0-9]+ (shell|monitor|task)s?' )
  if [ "$st" = blocked ]; then cur=BLOCKED
  elif [ "$st" = working ] || [ "$sub" -gt 0 ] || [ "$spin" -gt 0 ] || [ "$bg" -gt 0 ]; then cur="WORKING(main=$st subagents=$sub bgtasks=$bg)"
  else cur=IDLE; fi
  # emit on category change only (WORKING/IDLE/BLOCKED); sub-state flips (bg task start/stop) are noise
  [ "${cur%%\(*}" != "${prev%%\(*}" ] && echo "$name: $cur"
  prev=$cur
  case $cur in
    BLOCKED) echo "$name: needs input — check pane"; exit 0;;
    IDLE) settled=$((settled+1)); [ $settled -ge 2 ] && { echo "$name: DONE (idle, no subagents, 2 polls)"; exit 0; };;
    *) settled=0;;
  esac
  sleep $poll
done
