#!/bin/bash
# Toggle orchestrator mode on/off
# Usage: tools/orchestrator-toggle.sh [on|off|status]
#
# Orchestrator mode restricts the main Claude Code thread to read-only + delegation.
# Only subagents (executor, etc.) can edit/write files.
# Toggle is instant -- no Claude Code restart required.

SENTINEL=".claude/orchestrator-mode"

case "${1:-toggle}" in
  on)
    touch "$SENTINEL"
    echo "Orchestrator mode: ON"
    echo "Main thread restricted to read + delegate. Use executor agent for changes."
    ;;
  off)
    rm -f "$SENTINEL"
    rm -f ".claude/orchestrator-session"
    echo "Orchestrator mode: OFF"
    echo "Main thread has full access."
    ;;
  status)
    if [ -f "$SENTINEL" ]; then
      echo "ON"
    else
      echo "OFF"
    fi
    ;;
  toggle)
    if [ -f "$SENTINEL" ]; then
      rm -f "$SENTINEL"
      rm -f ".claude/orchestrator-session"
      echo "Orchestrator mode: OFF"
    else
      touch "$SENTINEL"
      echo "Orchestrator mode: ON"
    fi
    ;;
  *)
    echo "Usage: $0 [on|off|status|toggle]"
    exit 1
    ;;
esac
