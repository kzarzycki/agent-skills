#!/usr/bin/env bash
# #1491: the skill text points host steps over SSH at the helper.
set -euo pipefail
grep -q 'omnigent_agent.py ssh <host> --why' engineering/skills/orchestrating-agents/backends/omnigent.md
grep -q 'ssh --why' engineering/skills/orchestrating-agents/SKILL.md
grep -q 'omnigent_agent.py ssh <host> --why' engineering/skills/engineering-loop/SKILL.md
