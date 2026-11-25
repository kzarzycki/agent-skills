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
# #2429: forms the first guard let through, one rule per family
REFUSED_2429 = [
    # a bare `environ` after `from os import environ`, and os.environb
    "python3 -c 'from os import environ; print(environ)'",
    "python3 -c 'from os import path, environ; print(dict(environ))'",
    "python3 -c \"from os import environ; print(environ['GH_TOKEN'])\"",
    "python3 -c 'import os; print(os.environb)'",
    "python3 -c \"import os; print(os.environb[b'GH_TOKEN'])\"",
    # wrappers that run a bare dump
    "find . -maxdepth 0 -exec env \\;",
    "find . -maxdepth 0 -exec env {} +",
    "find . -execdir printenv GH_TOKEN {} \\;",
    "find . -name x | xargs env",
    "echo x | xargs -n1 printenv",
    # one step of variable indirection
    "x=$GITHUB_TOKEN; echo $x",
    'x="${GH_TOKEN}"; echo "$x"',
    "x=$GITHUB_TOKEN\necho $x",
    "x=$GITHUB_TOKEN; y=$x; printf '%s' \"$y\"",
    "export x=$GITHUB_TOKEN; echo $x",
    "x=$GITHUB_TOKEN; eval 'echo $x'",
    "x=$GITHUB_TOKEN; cat <<< $x",
    # curl prints the request headers in verbose and trace modes
    'curl -v -H "Authorization: Bearer $GITHUB_TOKEN" https://example.invalid',
    'curl --verbose -H "Authorization: Bearer $GITHUB_TOKEN" https://example.invalid',
    'curl -sSv -H "Authorization: Bearer $GITHUB_TOKEN" https://example.invalid',
    'curl --trace-ascii - -H "Authorization: Bearer $GITHUB_TOKEN" https://example.invalid',
    'curl -v -u "me:$GH_TOKEN" https://example.invalid',
    'x=$GH_TOKEN; curl -v -H "Authorization: Bearer $x" https://example.invalid',
    # a one-liner that still dumps through a string starting with set/export/env
    "python3 -c \"import os; os.system('env | sort')\"",
    "python3 -c \"import os; os.system('export -p')\"",
    "python3 -c \"import os; os.system('set')\"",
    "python3 -c \"import subprocess; subprocess.run('env', shell=True)\"",
    "python3 -c \"import subprocess; subprocess.run(['env'])\"",
    "python3 -c \"import os; os.system('env > /dev/stdout')\"",
    # review of #2441: a redirect with an fd, and `env` with options or assignments but no command
    "python3 -c \"import subprocess; subprocess.run('env 2>&1', shell=True)\"",
    "python3 -c \"import os; os.system('env 1>&2')\"",
    "python3 -c \"import os; os.system('env -u HOME')\"",
    "python3 -c \"import os; os.system('env FOO=1')\"",
    "python3 -c \"import subprocess; subprocess.run(['env','--null'])\"",
    "python3 -c \"import subprocess; subprocess.run(['env', '-0'])\"",
    "python3 -c \"import subprocess; subprocess.run(['env', '-u', 'HOME'])\"",
    "python3 -c \"import subprocess; subprocess.run(['env', 'FOO=1'])\"",
    "python3 -c \"import subprocess; subprocess.check_output(['printenv', 'GH_TOKEN'])\"",
]
PASSED_2429 = [
    # a one-liner whose command string only starts with set, export or env
    "python3 -c \"import subprocess; subprocess.run('set -e; make', shell=True)\"",
    "python3 -c \"import os; os.system('export FOO=1; make')\"",
    "python3 -c \"import subprocess; subprocess.run(['env', 'FOO=1', 'ls'])\"",
    "python3 -c \"import subprocess; subprocess.run(['env','FOO=1','ls'])\"",
    "python3 -c \"import subprocess; subprocess.check_call('env FOO=1 make', shell=True)\"",
    "python3 -c \"import os; os.system('env -u HOME make')\"",
    "python3 -c \"import subprocess; subprocess.run(['env', '-u', 'HOME', 'ls'])\"",
    # the same names that are no dump
    "python3 -c 'from os import environ; print(environ[\"HOME\"])'",
    "python3 -c 'from os import environ; print(len(environ))'",
    "python3 -c \"from os import environ; print(environ.get('HOME'))\"",
    "python3 -c \"import os; print(os.environb[b'HOME'])\"",
    "python3 -c 'print(environ)'",
    "find . -name '*.py' -exec grep -l foo {} +",
    "find . -exec env FOO=1 ls {} \\;",
    "x=$HOME; echo $x",
    "x=$GITHUB_TOKEN; echo $x | wc -c",
    'x=$GITHUB_TOKEN; echo "${#x}"',
    "x=1; echo $x",
    "x=$GITHUB_TOKEN; x=1; echo $x",
    "x=$GITHUB_TOKEN; unset x; echo $x",
    "curl -v https://example.invalid",
    'curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://example.invalid',
    'curl --verbose -H "Accept: json" https://example.invalid',
]
REFUSED += REFUSED_2429
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
    "awk 'BEGIN{print ENVIRON[\"HOME\"]}'",
    "python3 -c \"import os; print('X' not in os.environ)\"",
    "python3 -c \"import os; print('HOME' in os.environ)\"",
    "python3 -c \"import os; print(os.environ.get('HOME'))\"",
    "python3 -c \"import os; print(os.getenv('EDITOR'))\"",
    "cat <<< $HOME",
    "bash <<'X'\nls\nX",
    "echo ls | sh",
    "eval echo hi",
    "",
]
PASSED += PASSED_2429


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
