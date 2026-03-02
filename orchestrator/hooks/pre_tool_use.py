#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///

import json
import sys
import re
from pathlib import Path

def is_dangerous_rm_command(command):
    """
    Comprehensive detection of dangerous rm commands.
    Matches various forms of rm -rf and similar destructive patterns.
    """
    # Normalize command by removing extra spaces and converting to lowercase
    normalized = ' '.join(command.lower().split())

    # Pattern 1: Standard rm -rf variations
    patterns = [
        r'\brm\s+.*-[a-z]*r[a-z]*f',  # rm -rf, rm -fr, rm -Rf, etc.
        r'\brm\s+.*-[a-z]*f[a-z]*r',  # rm -fr variations
        r'\brm\s+--recursive\s+--force',  # rm --recursive --force
        r'\brm\s+--force\s+--recursive',  # rm --force --recursive
        r'\brm\s+-r\s+.*-f',  # rm -r ... -f
        r'\brm\s+-f\s+.*-r',  # rm -f ... -r
    ]

    # Check for dangerous patterns
    for pattern in patterns:
        if re.search(pattern, normalized):
            return True

    # Pattern 2: Check for rm with recursive flag targeting dangerous paths
    dangerous_paths = [
        r'/',           # Root directory
        r'/\*',         # Root with wildcard
        r'~',           # Home directory
        r'~/',          # Home directory path
        r'\$HOME',      # Home environment variable
        r'\.\.',        # Parent directory references
        r'\*',          # Wildcards in general rm -rf context
        r'\.',          # Current directory
        r'\.\s*$',      # Current directory at end of command
    ]

    if re.search(r'\brm\s+.*-[a-z]*r', normalized):  # If rm has recursive flag
        for path in dangerous_paths:
            if re.search(path, normalized):
                return True

    return False

def is_env_file_access(tool_name, tool_input):
    """
    Check if any tool is trying to access .env files containing sensitive data.
    """
    if tool_name in ['Read', 'Edit', 'MultiEdit', 'Write', 'Bash']:
        # Check file paths for file-based tools
        if tool_name in ['Read', 'Edit', 'MultiEdit', 'Write']:
            file_path = tool_input.get('file_path', '')
            if '.env' in file_path and not file_path.endswith('.env.sample'):
                return True

        # Check bash commands for .env file access
        elif tool_name == 'Bash':
            command = tool_input.get('command', '')
            # Pattern to detect .env file access (but allow .env.sample)
            env_patterns = [
                r'\b\.env\b(?!\.sample)',  # .env but not .env.sample
                r'cat\s+.*\.env\b(?!\.sample)',  # cat .env
                r'echo\s+.*>\s*\.env\b(?!\.sample)',  # echo > .env
                r'touch\s+.*\.env\b(?!\.sample)',  # touch .env
                r'cp\s+.*\.env\b(?!\.sample)',  # cp .env
                r'mv\s+.*\.env\b(?!\.sample)',  # mv .env
            ]

            for pattern in env_patterns:
                if re.search(pattern, command):
                    return True

    return False

def is_orchestrator_mode():
    """Check if orchestrator mode is active (sentinel file exists)."""
    return (Path.cwd() / '.claude' / 'orchestrator-mode').exists()


def is_main_orchestrator_session(hook_input):
    """Check if this tool call is from the main orchestrator session.
    Reads the session ID stored when orchestrator mode was activated.
    If no sentinel file exists, falls back to transcript_path heuristic."""
    sentinel = Path.cwd() / '.claude' / 'orchestrator-session'
    if sentinel.exists():
        main_session_id = sentinel.read_text().strip()
        current_session_id = hook_input.get('session_id', '')
        return current_session_id == main_session_id
    # Fallback: old heuristic (subagents have /subagents/ in transcript path)
    transcript = hook_input.get('transcript_path', '')
    return '/subagents/' not in transcript


def is_write_tool(tool_name):
    """Check if tool is a file-writing tool."""
    return tool_name in ('Edit', 'Write', 'MultiEdit')


# Bash commands that are always allowed in orchestrator mode (read-only / coordination)
BASH_SAFE_PREFIXES = [
    'git ', 'gh ', 'ls', 'cat ', 'head ', 'tail ', 'find ', 'grep ', 'rg ',
    'uv run pytest', 'uv run mypy', 'uv sync', 'lean ', 'tmux ', 'rodney ',
    'python -m analytics', 'bd ', 'echo ', 'wc ', 'diff ', 'which ', 'pwd',
    'env ', 'printenv', 'date', 'whoami', 'hostname', 'df ', 'du ',
    'ps ', 'top ', 'htop', 'free ', 'uptime', 'id ',
    'npm list', 'npm --version', 'npm view', 'npx ',
    'npm run build', 'npm run dev',
    'jq ', 'sort ', 'uniq ', 'cut ', 'tr ', 'awk ',
    'curl ', 'wget ',  # read-only fetches
    'sleep ',
]

# Bash patterns that indicate file writes (blocked in orchestrator mode)
BASH_WRITE_PATTERNS = [
    r'(?<![<\w@.])>\s*[/\w~.]',  # > redirect to file (avoid matching emails/heredocs)
    r'>>\s',             # >> append
    r'\btee\b',          # tee command
    r'\bsed\s+.*-i',    # sed in-place
    r'\btouch\b',        # create file
    r'\bmkdir\b',        # create directory
    r'\bcp\b',           # copy files
    r'\bmv\b',           # move/rename files
    r'\bchmod\b',        # change permissions (file mutation)
    r'\binstall\b',      # install commands
    r'\bnpm install',    # install dependencies
    r'\bpip install',    # pip install
]


def classify_bash_command(command):
    """Classify a bash command for orchestrator mode.
    Returns: 'allow', 'block', or 'warn'."""
    cmd = command.strip()

    # Safe prefixes first — trusted commands are always allowed
    for prefix in BASH_SAFE_PREFIXES:
        if cmd.startswith(prefix):
            return 'allow'

    # Write patterns block unknown commands that mutate files
    for pattern in BASH_WRITE_PATTERNS:
        if re.search(pattern, cmd):
            return 'block'

    # Unknown commands: warn but allow
    return 'warn'


def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)

        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        # Check for .env file access (blocks main orchestrator session only; agents need .env for data imports)
        if is_env_file_access(tool_name, tool_input):
            if not is_orchestrator_mode() or is_main_orchestrator_session(input_data):
                print("BLOCKED: Access to .env files containing sensitive data is prohibited", file=sys.stderr)
                print("Use .env.sample for template files instead", file=sys.stderr)
                sys.exit(2)  # Exit code 2 blocks tool call and shows error to Claude

        # Check for dangerous rm -rf commands
        if tool_name == 'Bash':
            command = tool_input.get('command', '')

            # Block rm -rf commands with comprehensive pattern matching
            if is_dangerous_rm_command(command):
                print("BLOCKED: Dangerous rm command detected and prevented", file=sys.stderr)
                sys.exit(2)  # Exit code 2 blocks tool call and shows error to Claude

        # Orchestrator mode enforcement (main thread only)
        if is_orchestrator_mode() and is_main_orchestrator_session(input_data):
            if is_write_tool(tool_name):
                file_path = tool_input.get('file_path', '')
                # Allow writes to plan files (plan mode needs to edit these)
                if not file_path.startswith(str(Path.home() / '.claude' / 'plans')):
                    print("BLOCKED: Orchestrator mode active. Delegate file changes to executor agent via Task().", file=sys.stderr)
                    sys.exit(2)

            if tool_name == 'Bash':
                command = tool_input.get('command', '')
                result = classify_bash_command(command)
                if result == 'block':
                    print("BLOCKED: Orchestrator mode active. Delegate write commands to executor agent via Task().", file=sys.stderr)
                    sys.exit(2)
                elif result == 'warn':
                    print("WARNING: Orchestrator mode active. Consider delegating this command to an agent.", file=sys.stderr)
                    # Allow but warn (exit 0, not 2)

        # Ensure log directory exists
        log_dir = Path.cwd() / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / 'pre_tool_use.json'

        # Read existing log data or initialize empty list
        if log_path.exists():
            with open(log_path, 'r') as f:
                try:
                    log_data = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    log_data = []
        else:
            log_data = []

        # Append new data
        log_data.append(input_data)

        # Write back to file with formatting
        with open(log_path, 'w') as f:
            json.dump(log_data, f, indent=2)

        sys.exit(0)

    except json.JSONDecodeError:
        # Gracefully handle JSON decode errors
        sys.exit(0)
    except Exception:
        # Handle any other errors gracefully
        sys.exit(0)

if __name__ == '__main__':
    main()
