"""The engineering pack's PreToolUse hook refuses a command that prints the whole environment or a
secret variable's value, and passes ordinary uses (#2359)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
SCRIPT = HOOKS / "secret_env_guard.py"
sys.path.insert(0, str(HOOKS))
spec = importlib.util.spec_from_file_location("secret_env_guard", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

REFUSED = [
    "env",
    "env -0",
    "printenv",
    "set",
    "export -p",
    "export",
    "declare -p",
    "declare -x",
    "typeset -x",
    "cat /proc/self/environ",
    "cat /proc/1234/environ | tr '\\0' '\\n'",
    "tr '\\0' '\\n' < /proc/self/environ",
    "strings /proc/$$/environ",
    "printenv CODEX_AUTH_JSON",
    "printenv GITHUB_TOKEN",
    "printenv AWS_SECRET_ACCESS_KEY",
    "printenv DB_PASSWORD",
    "declare -p API_KEY",
    'echo "$CODEX_AUTH_JSON"',
    "echo ${GITHUB_TOKEN}",
    "printf '%s' \"$MY_SECRET\"",
    "env | grep TOKEN",
    "printenv | sort",
    "cd /tmp && env",
    "git fetch; env",
    "bash -c 'env'",
    "sh -c \"bash -c 'printenv'\"",
    "sudo env",
    "echo $(printenv API_KEY)",
    "python3 -c 'import os; print(os.environ)'",
    "python3 -c 'import os; print(dict(os.environ))'",
    "python3 -c \"import os; print(os.environ['MY_TOKEN'])\"",
    "node -e 'console.log(process.env)'",
    "node -e 'console.log(process.env.NPM_TOKEN)'",
    # review of #2363: indirection through wrappers, substitutions, stdin code and readers
    "cat <(env)",
    "echo `env`",
    "nice env",
    "nice -n 5 printenv",
    "busybox env",
    "eval env",
    "eval 'echo $GITHUB_TOKEN'",
    "grep TOKEN /proc/self/environ",
    "awk 'BEGIN{for(k in ENVIRON)print k,ENVIRON[k]}'",
    "python3 <<X\nimport os;print(os.environ)\nX",
    "python3 - <<X\nprint(os.environ['API_KEY'])\nX",
    # review pass 2 of #2363: the lookup idiom, here-strings, a shell fed on stdin, odd /proc paths
    "python3 -c \"import os; print(os.environ.get('GH_TOKEN'))\"",
    "python3 -c \"import os; print(os.environ.get('CODEX_AUTH_JSON'))\"",
    "python3 -c \"import os; print(os.getenv('GH_TOKEN'))\"",
    "python3 -c 'import os\nfor k,v in os.environ.items(): print(k,v)'",
    "python3 -c 'import os\nfor k in os.environ: print(k, os.environ[k])'",
    "python3 -c \"import os; print([f'{k}={v}' for k,v in os.environ.items()])\"",
    "python3 - <<X\nimport os\nfor k in os.environ: print(k)\nX",
    "node -e 'for (const k in process.env) console.log(k)'",
    "awk 'BEGIN{print ENVIRON[\"GH_TOKEN\"]}'",
    "cat <<< $GH_TOKEN",
    "tee /dev/stdout <<< $GH_TOKEN",
    "echo env | sh",
    "bash <<< 'env'",
    "bash <<'X'\nprintenv GH_TOKEN\nX",
    "cat /proc/self/task/1/environ",
    "cat /proc/self/./environ",
    "ruby -e 'p ENV'",
    "python3 -c \"print(open('/proc/self/environ').read())\"",
    "python3 -c \"import os; os.system('env')\"",
    "python3 -c \"import subprocess; print(subprocess.check_output('env'))\"",
]
PASSED = [
    "env FOO=1 cmd",
    "env -u HOME ls",
    "FOO=1 env BAR=2 python3 x.py",
    "printenv HOME",
    "printenv PATH",
    "printenv CODEX_AUTH_JSON | wc -c",
    "printenv CODEX_AUTH_JSON | sha256sum | cut -c1-8",
    'echo "$GITHUB_TOKEN" | sha256sum',
    'echo -n "$GITHUB_TOKEN" | wc -c',
    'echo "${#CODEX_AUTH_JSON}"',
    'printf "%s" "${#API_KEY}"',
    'echo "$HOME"',
    'echo "$GIT_AUTHOR_NAME"',
    'echo "$SSH_AUTH_SOCK"',
    'for key in a b; do echo "$key"; done',
    '[ -n "${GITHUB_TOKEN-}" ] && echo set',
    "env | wc -l",
    "env | grep -q TOKEN",
    "compgen -e",
    "set -e",
    "set -euo pipefail",
    "export FOO=1",
    "export -n FOO",
    "declare -p HOME",
    "declare -a arr=(1 2)",
    "ls /proc/self",
    "grep -rn '/proc/self/environ' src",
    'curl -H "Authorization: Bearer $GITHUB_TOKEN" https://example.invalid',
    "git status",
    "python3 -c 'import os; print(os.environ[\"HOME\"])'",
    'python3 -c \'import os; print(len(os.environ.get("API_KEY", "")))\' ',
    "node -e 'console.log(process.env.HOME)'",
    "python3 script.py",
    # review of #2363: text that only mentions the files and names is data
    'git commit -m "$(cat <<EOF\nrefuse < /proc/1/environ\nEOF\n)"',
    'echo "see /proc/self/environ"',
    'git commit -m "guard reads /proc/self/environ and printenv"',
    "git log -- /proc/self/environ",
    "grep -q TOKEN /proc/self/environ",
    'echo "${GH_TOKEN:+set}"',
    'echo "${GH_TOKEN+set}"',
    'echo "$TOKENIZER"',
    "python3 <<X\nimport sys;print(sys.argv)\nX",
    "awk '{print ENVIRON[\"HOME\"]}' f",
    "nice make",
    "python3 -c \"import os,subprocess; e=os.environ.copy(); e['A']='1'; print(subprocess.run(['true'],env=e).returncode)\"",
    "python3 -c \"import os; print('HOME' in os.environ)\"",
    'python3 -c "import os; print(len(os.environ))"',
    "python3 - <<'X'\nimport os,subprocess\nenv = dict(os.environ, A=\"1\")\nprint(subprocess.run(['true'], env=env).returncode)\nX",
    'node -e "const e={...process.env}; console.log(Object.keys(e).length)"',
    "python3 - <<'X'\nprint(\"os.environ is used\")\nX",
    "echo $PUBLIC_KEY",
    "echo $KEY_ID",
    "echo $TOKEN_COUNT",
    "printf '%s' \"$API_KEY_NAME\"",
    "awk 'BEGIN{print ENVIRON[\"HOME\"]}'",
    "python3 -c \"import os; print('X' not in os.environ)\"",
    "python3 -c \"import os; print(os.environ.get('HOME'))\"",
    "python3 -c \"import os; print(os.getenv('EDITOR'))\"",
    "cat <<< $HOME",
    "bash <<'X'\nls\nX",
    "echo ls | sh",
    "eval echo hi",
    "",
]


@pytest.mark.parametrize("command", REFUSED)
def test_a_dump_or_a_secret_print_is_refused(command: str) -> None:
    code, line = guard.verdict({"tool_name": "Bash", "tool_input": {"command": command}})
    assert code == 2, command
    assert "compgen -e" in line and "sha256sum" in line and "wc -c" in line


@pytest.mark.parametrize("command", PASSED)
def test_an_ordinary_use_passes(command: str) -> None:
    code, line = guard.verdict({"tool_name": "Bash", "tool_input": {"command": command}})
    assert (code, line) == (0, ""), command


def run(payload: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_hook_exits_2_with_the_reason_on_stderr() -> None:
    done = run({"tool_name": "Bash", "tool_input": {"command": "printenv"}})
    assert done.returncode == 2 and "secret_env_guard" in done.stderr and done.stdout == ""


def test_bad_input_is_allowed() -> None:
    for raw in ("not json", "[]", "{}", '{"tool_input": 5}'):
        done = subprocess.run(
            [sys.executable, str(SCRIPT)], input=raw, capture_output=True, text=True, check=False
        )
        assert done.returncode == 0, raw


def test_another_tool_is_left_alone() -> None:
    assert guard.verdict({"tool_name": "Read", "tool_input": {"command": "env"}}) == (0, "")


def test_both_guards_are_registered_for_every_session() -> None:
    manifest = json.loads((HOOKS / "hooks-claude.json").read_text())
    commands = [h["command"] for e in manifest["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("secret_env_guard.py" in c for c in commands)
    settings = json.loads((HOOKS.parents[1] / ".claude" / "settings.json").read_text())
    own = [h["command"] for e in settings["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("secret_env_guard.py" in c for c in own)
    deployed = HOOKS.parents[1] / ".claude/hooks/engineering/hooks/secret_env_guard.py"
    assert deployed.read_text() == SCRIPT.read_text()


def test_a_command_it_cannot_parse_is_allowed() -> None:
    done = run({"tool_name": "Bash", "tool_input": {"command": "echo 'unterminated"}})
    assert done.returncode == 0


def test_the_hook_parses_on_the_oldest_python3_a_consumer_has() -> None:
    import ast

    ast.parse(SCRIPT.read_text(), feature_version=(3, 9))
