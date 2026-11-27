#!/usr/bin/env bash
# #1491: the skill text points host steps over SSH at the helper.
set -euo pipefail
# the omnigent backend's text now lives in omnigent-agents' SKILL.md, where the line wraps
tr '\n' ' ' < omnigent/skills/omnigent-agents/SKILL.md | grep -q 'omnigent_agent.py ssh <host> --why'
grep -q 'ssh --why' engineering/skills/orchestrating-agents/SKILL.md
grep -q 'omnigent_agent.py ssh <host> --why' loop/skills/engineering-loop/SKILL.md
