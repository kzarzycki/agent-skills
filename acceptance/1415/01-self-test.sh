#!/bin/sh
# claude-ai-import: parses a made-up chat and project with no network; GET-only and
# background-tab checks read the network layer's source. The live pulls need a logged-in
# browser and a private chat, so they stay Manual (see the PR's Before merge list).
exec python3 research/skills/claude-ai-import/scripts/claude_ai_import.py self-test
