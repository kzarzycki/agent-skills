#!/bin/bash
# Flow session bootstrap hook (optional)
# Reads .work/ state and injects it as additionalContext on session start.
# Install via: copy to .claude/hooks/flow-bootstrap.sh, register in .claude/settings.json

WORK_DIR=".work"

if [ ! -d "$WORK_DIR" ]; then
  exit 0
fi

CONTEXT=""

# Read brief (first 20 lines for summary)
if [ -f "$WORK_DIR/brief.md" ]; then
  BRIEF=$(head -20 "$WORK_DIR/brief.md")
  CONTEXT="## Project Brief\n$BRIEF\n\n"
fi

# Scan work stream ITEM.md files for non-done items
for item_file in "$WORK_DIR"/*/ITEM.md; do
  [ -f "$item_file" ] || continue
  stream_name=$(basename "$(dirname "$item_file")")
  # Skip if status is "done"
  if grep -qi "^## Status:.*done" "$item_file" 2>/dev/null; then
    continue
  fi
  ITEM=$(cat "$item_file")
  CONTEXT="${CONTEXT}## Work Stream: $stream_name\n$ITEM\n\n"
done

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
