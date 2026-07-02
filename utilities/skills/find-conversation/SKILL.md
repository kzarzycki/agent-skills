---
name: find-conversation
description: "Search past Claude Code conversations (JSONL session history) by topic, content, date, or working directory."
when_to_use: "Finding a previous conversation, recalling what was discussed, locating a session, or resuming past work — 'find that conversation', 'we talked about X before', 'resume that session'."
---

# Find Conversation Skill

Search through past Claude Code conversation history stored as JSONL files.

## Storage Architecture

- **Location:** `~/.claude/projects/{encoded-cwd}/{sessionId}.jsonl`
- **Encoding:** Working directory path with `/` → `-`, spaces → `-` (e.g., `-Users-zarz-dev-kb-personal`, `-Users-zarz-dev-projects-daitw-2026`; older sessions encoded under `-Users-zarz-dev-life-os` before the multi-repo split)
- **Naming:** Each file is `{UUID}.jsonl` — the UUID is the session ID
- **Total:** ~941 sessions across ~26 project directories
- **Size range:** 387 bytes to 43 MB

## JSONL Record Schema

Each line is a JSON object:

```json
{
  "sessionId": "UUID",
  "type": "user|assistant|system|progress|last-prompt|file-history-snapshot",
  "timestamp": "ISO 8601 UTC",
  "cwd": "/working/directory",
  "version": "2.1.73",
  "gitBranch": "master",
  "isMeta": false,
  "message": {
    "role": "user|assistant",
    "content": "string or array"
  }
}
```

## Search Strategy (follow this order)

### Step 1: Quick CLI list

Run `claude --resume` non-interactively to get recent sessions with their first messages. This is the fastest way to scan recent work:

```bash
# List recent sessions (pipe to grep to search)
echo "" | claude --resume 2>&1 | head -50
```

If this doesn't work well non-interactively, skip to Step 2.

### Step 2: Grep JSONL files directly

Search across ALL project directories. **Never filter by file mtime** — sessions can span days and mtime reflects last write, not content dates.

```bash
# Search for keywords in user messages across all sessions
grep -rl "search term" ~/.claude/projects/*/  --include="*.jsonl" | head -20

# For more targeted search (user messages only)
grep -l '"type":"user".*search term' ~/.claude/projects/*/*.jsonl
```

Use multiple keyword variants — the user may describe the topic differently than how it appeared in the conversation.

### Step 3: Extract session metadata from matches

For each matching file, extract context:

```bash
# Get session ID from filename
basename /path/to/session.jsonl .jsonl

# Get first user message (skip isMeta records)
python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    for line in f:
        r = json.loads(line)
        if r.get('type') == 'user' and not r.get('isMeta'):
            content = r['message'].get('content', '')
            if isinstance(content, list):
                content = ' '.join(c.get('text','') for c in content if c.get('type')=='text')
            print(f\"First msg ({r['timestamp']}): {content[:200]}\")
            break
" /path/to/session.jsonl

# Get working directory
python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    r = json.loads(f.readline())
    print(f\"CWD: {r.get('cwd', 'unknown')}\")
" /path/to/session.jsonl

# Get date range (first and last timestamps)
python3 -c "
import json, sys
lines = open(sys.argv[1]).readlines()
first = json.loads(lines[0])
last = json.loads(lines[-1])
print(f\"Range: {first.get('timestamp','?')} → {last.get('timestamp','?')}\")
" /path/to/session.jsonl
```

### Step 4: If topic was compacted away

Long sessions get compacted — content from early in the session may not appear in grep results because it was summarized/removed. If you suspect this:

1. Check the plan files — plans survive compaction: `grep -rl "keyword" ~/.claude/plans/*.md`
2. Look for sessions in the right project directory with timestamps in the right date range
3. Extract ALL user messages from candidate sessions and scan them
4. Check for `type: "system"` records with compaction markers

### Step 5: Present results to user

For each candidate session, show:
- Session ID
- Working directory
- First user message (truncated)
- Date range
- Why this might be the right one

Let the user pick. Then offer to open it:

```bash
# Resume in current terminal
claude --resume {sessionId}

# Resume in new tmux window
tmux new-window -n "session-name" "cd {cwd} && claude --resume {sessionId}"
```

## Critical Rules

1. **NEVER filter by file modification time (mtime)** — sessions span days; mtime only reflects last write
2. **Search ALL project directories** — the user may not remember which working directory they used
3. **Use multiple search terms** — try topic keywords, proper nouns, tool names, file paths
4. **Account for compaction** — early content in long sessions gets summarized and original text is lost from the JSONL
5. **Check plan files too** — `~/.claude/plans/*.md` persist even when conversation context is compacted
6. **Don't confuse the current session** — check that a match isn't the session you're currently running in
7. **Use subagents for search** — delegate JSONL scanning to Explore agents to keep main context clean
8. **Present, don't guess** — show candidates to the user rather than assuming which one is correct
