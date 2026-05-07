# Orchestrator Setup

Install orchestrator mode into a project. Run these steps:

## 1. Copy hook

Copy the PreToolUse hook from the skill directory into the project. The skill may be installed at project level (`.claude/skills/orchestrator/`) or globally (`~/.claude/skills/orchestrator/`):

```bash
SKILL_DIR="$([ -d .claude/skills/orchestrator ] && echo .claude/skills/orchestrator || echo $HOME/.claude/skills/orchestrator)"
mkdir -p .claude/hooks && cp "$SKILL_DIR/hooks/pre_tool_use.py" .claude/hooks/pre_tool_use.py && chmod +x .claude/hooks/pre_tool_use.py
```

## 2. Copy toggle script

```bash
SKILL_DIR="$([ -d .claude/skills/orchestrator ] && echo .claude/skills/orchestrator || echo $HOME/.claude/skills/orchestrator)"
mkdir -p tools && cp "$SKILL_DIR/scripts/orchestrator-toggle.sh" tools/orchestrator-toggle.sh && chmod +x tools/orchestrator-toggle.sh
```

## 3. Register hook in settings.json

Create or update `.claude/settings.json`. If the file exists, merge the PreToolUse hook entry — do not overwrite existing hooks (e.g. flow's SessionStart).

The hook entry to add:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/pre_tool_use.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## 4. Update .gitignore

Add `logs/` to `.gitignore` if not already present (the hook logs tool calls there).

## 5. Confirm

Report: "Orchestrator set up. Use `/orchestrator on` to activate."
