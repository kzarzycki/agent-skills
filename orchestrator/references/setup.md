# Orchestrator Setup

Install orchestrator mode into a project. Run these steps:

## 1. Copy hook

Copy the PreToolUse hook from the skill directory into the project:

```bash
mkdir -p .claude/hooks
cp .claude/skills/orchestrator/hooks/pre_tool_use.py .claude/hooks/pre_tool_use.py
chmod +x .claude/hooks/pre_tool_use.py
```

## 2. Copy toggle script

```bash
mkdir -p tools
cp .claude/skills/orchestrator/scripts/orchestrator-toggle.sh tools/orchestrator-toggle.sh
chmod +x tools/orchestrator-toggle.sh
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
