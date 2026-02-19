#!/bin/bash
# Flow session bootstrap hook
# Reads .work/ state and injects it as additionalContext on session start.
# Installed by /flow:init into .claude/hooks/

WORK_DIR=".work"

if [ ! -d "$WORK_DIR" ]; then
  exit 0
fi

CONTEXT=""

# Read brief (first 10 lines for summary)
if [ -f "$WORK_DIR/brief.md" ]; then
  BRIEF=$(head -20 "$WORK_DIR/brief.md")
  CONTEXT="## Project Brief\n$BRIEF\n\n"
fi

# Read state
if [ -f "$WORK_DIR/state.md" ]; then
  STATE=$(cat "$WORK_DIR/state.md")
  CONTEXT="${CONTEXT}## Current State\n$STATE\n\n"
fi

# Read active item's ITEM.md if there is one
if [ -f "$WORK_DIR/state.md" ]; then
  ACTIVE=$(grep -i "^Active Item:" "$WORK_DIR/state.md" | sed 's/Active Item: *//' | tr -d '[:space:]')
  if [ -n "$ACTIVE" ] && [ "$ACTIVE" != "none" ] && [ -f "$WORK_DIR/items/$ACTIVE/ITEM.md" ]; then
    ITEM=$(cat "$WORK_DIR/items/$ACTIVE/ITEM.md")
    CONTEXT="${CONTEXT}## Active Item: $ACTIVE\n$ITEM\n\n"
  fi
fi

# Read last 5 log entries
if [ -f "$WORK_DIR/log.md" ]; then
  LOG=$(tail -6 "$WORK_DIR/log.md")
  CONTEXT="${CONTEXT}## Recent Log\n$LOG"
fi

if [ -z "$CONTEXT" ]; then
  exit 0
fi

# Escape for JSON
ESCAPED=$(printf '%s' "$CONTEXT" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')

cat <<EOF
{"hookSpecificOutput": {"additionalContext": $ESCAPED}}
EOF
