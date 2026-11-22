"""The engineering pack's PreToolUse hook refuses a build, test, gate, land or git push run on
another machine over ssh (#1754)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
SCRIPT = HOOKS / "remote_run_guard.py"
spec = importlib.util.spec_from_file_location("remote_run_guard", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

# each refused form, with what the refusal calls it
REFUSED = {
    # builds and tests
    "ssh box make": "build or test",
    "ssh box make -j8 install": "build or test",
    "ssh box mise run check": "build or test",
    "ssh box mise r test": "build or test",
    "ssh box mise tasks run lint": "build or test",
    "ssh box pytest -q": "build or test",
    "ssh box pytest tests/test_a.py": "build or test",  # one file on a host is still a run there
    "ssh box python3 -m pytest": "build or test",
    "ssh box uv run pytest": "build or test",
    "ssh box uv run --with x python -m pytest -x": "build or test",
    "ssh box xcodebuild -scheme App test": "build or test",
    "ssh box ./gradlew build": "build or test",
    "ssh box gradle test": "build or test",
    "ssh box mvn verify": "build or test",
    "ssh box npm test": "build or test",
    "ssh box npm run build": "build or test",
    "ssh box npm ci": "build or test",
    "ssh box pnpm install": "build or test",
    "ssh box yarn test": "build or test",
    "ssh box cargo build --release": "build or test",
    "ssh box go test ./...": "build or test",
    "ssh box swift build": "build or test",
    "ssh box dotnet test": "build or test",
    "ssh box tox -e py314": "build or test",
    "ssh box nox": "build or test",
    "ssh box ninja -C out": "build or test",
    "ssh box cmake --build build": "build or test",
    "ssh box bazel test //...": "build or test",
    "ssh box just ci": "build or test",
    # gates and lands
    "ssh box uv run gatekeeper/skills/gatekeeper/scripts/approvals.py land 12": "gate or land",
    "ssh box python3 approvals.py local-ci 12 --run": "gate or land",
    "ssh box uv run approvals.py record verdict 12 report.md": "gate or land",
    "ssh box uv run approvals.py approve merge 12 --head abc --by delegate": "gate or land",
    "ssh box uv run approvals.py delegate 12": "gate or land",
    "ssh box uv run approvals.py affected-tests": "gate or land",
    "ssh box uv run approvals.py heavy make": "gate or land",
    "ssh box python3 gatekeeper.py land --wait": "gate or land",
    "ssh box mise run loop:land 12": "build or test",
    # git pushes
    "ssh box git push": "git push",
    "ssh box git push origin HEAD:refs/heads/x": "git push",
    "ssh box git -C /srv/repo push": "git push",
    "ssh box git -c user.name=x push --tags": "git push",
}

SPELLINGS = [
    # quoting: the remote command as one string, as several words, or both
    "ssh box 'make test'",
    'ssh box "make test"',
    "ssh box 'cd repo && make test'",
    'ssh box "cd ~/repo; git status; git push"',
    "ssh box 'git status;' make",
    # options, with and without values, joined and apart
    "ssh -o BatchMode=yes box 'make test'",
    "ssh -oBatchMode=yes box make",
    "ssh -o BatchMode=yes -o ConnectTimeout=5 box 'cd repo && pytest'",
    "ssh -p 2222 user@box make",
    "ssh -p2222 box make",
    "ssh -i ~/.ssh/key -l me box make",
    "ssh -tt box make",
    "ssh -At -J jump box make",
    "ssh -v -- box make",
    "/usr/bin/ssh box make",
    "autossh box make",
    # wrappers and chains around ssh, and shells on either side
    "timeout 600 ssh box make",
    "env FOO=1 ssh box make",
    "nohup ssh box make &",
    "git fetch && ssh box make",
    "cd /tmp && ssh box make",
    "bash -c 'ssh box make'",
    "sh -c \"ssh -o BatchMode=yes box 'make test'\"",
    "ssh box bash -lc 'make test'",
    "ssh box 'bash -c \"cd repo && make\"'",
    "ssh box 'nohup make > build.log 2>&1 &'",
    "ssh box 'FOO=1 make'",
    "ssh box 'env CI=1 timeout 60 make'",
    "ssh box 'if [ -d repo ]; then cd repo && make; fi'",
    "ssh box <<'EOF'\nls\nEOF\nssh box make",
    # orchestrating-agents' own ssh step
    "python3 scripts/omnigent_agent.py ssh box --why 'gate step' -- 'make test'",
    "python3 omnigent/skills/omnigent-agents/scripts/omnigent_agent.py ssh box -- make test",
    "uv run omnigent_agent.py ssh box --why push -- git push",
]

ALLOWED = [
    # read-only calls: they read a host's state and end at once, leaving nothing to track
    "ssh box cat /proc/loadavg",
    "ssh box uptime",
    "ssh box ps aux",
    "ssh box 'ps -eo pid,cmd | grep pytest'",  # a word naming a tool is no run of it
    "ssh box tail -n 50 /tmp/build.log",
    "ssh box 'tail -f ~/repo/tmp/loop/make.log'",
    "ssh box head -c 400 report.md",
    "ssh box cat ~/repo/tmp/loop/report.md",
    "ssh box 'grep -n FAILED ~/repo/tmp/loop/pytest.log'",
    "ssh box git log --oneline -5",
    "ssh box 'cd repo && git status'",
    "ssh box git -C repo rev-parse HEAD",
    "ssh box git fetch origin",
    "ssh box git diff --stat",
    "ssh box df -h",
    "ssh box ls ~/repo",
    "ssh box uv run approvals.py check merge 12",
    "ssh box python3 approvals.py report 12",
    "ssh box 'echo make test'",
    "python3 scripts/omnigent_agent.py ssh box --why load -- cat /proc/loadavg",
    # no remote command at all
    "ssh box",
    "ssh -N -L 8080:localhost:80 box",
    "ssh -O check box",
    "ssh -G box",
    "ssh -V",
    "ssh -s box sftp",
    # local runs and copies are not this hook's
    "make test",
    "git push origin HEAD",
    "pytest -q",
    "scp box:/tmp/build.log .",
    "rsync -a box:repo/ repo/",
    "echo 'ssh box make'",
    "cat <<'EOF'\nssh box make\nEOF",
    "grep -rn 'ssh box make' docs",
    "python3 scripts/omnigent_agent.py start --host box --brief b.md",
    # nothing it can parse
    "ssh box 'make",
    "",
]


def call(command: str, tool: str = "Bash") -> dict:
    return {"tool_name": tool, "tool_input": {"command": command}, "cwd": "/tmp"}


def run_hook(stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)], input=stdin, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(("command", "what"), REFUSED.items())
def test_each_remote_build_test_gate_land_or_push_is_refused(command: str, what: str) -> None:
    code, reason = guard.verdict(call(command))
    assert code == 2, command
    assert f"is a {what}." in reason and "over ssh to box" in reason


@pytest.mark.parametrize("command", SPELLINGS)
def test_every_spelling_of_the_ssh_call_is_seen(command: str) -> None:
    assert guard.verdict(call(command))[0] == 2, command


@pytest.mark.parametrize("command", ALLOWED)
def test_read_only_remote_calls_and_local_runs_stay_allowed(command: str) -> None:
    assert guard.verdict(call(command)) == (0, ""), command


def test_the_refusal_names_the_host_the_command_and_what_replaces_it() -> None:
    code, reason = guard.verdict(call("ssh -o BatchMode=yes me@box 'cd repo &&\n  make test'"))
    assert code == 2
    assert reason.startswith("Remote run refused: `cd repo && make test` over ssh to me@box")
    assert "omnigent_agent.py start --host <host>" in reason
    assert "claude-cloud-run" in reason
    assert "Mergify `land` and `record verdict`" in reason and "your own session" in reason
    assert "/proc/loadavg" in reason  # what stays allowed


def test_the_launcher_ssh_step_names_its_host() -> None:
    reason = guard.verdict(call("python3 omnigent_agent.py ssh box2 --why x -- make"))[1]
    assert "over ssh to box2" in reason


def test_only_bash_calls_are_judged() -> None:
    assert guard.verdict(call("ssh box make", tool="Read")) == (0, "")
    assert guard.verdict({"tool_input": {"command": "ssh box make"}})[0] == 2  # Bash by default
    assert guard.verdict({"tool_name": "Bash", "tool_input": {}}) == (0, "")
    assert guard.verdict({"tool_name": "Bash", "tool_input": {"command": 3}}) == (0, "")


def test_it_applies_in_a_cloud_session_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike heavy_run_guard, nothing about the session lets a remote run through."""
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("LOOP_HOST_RUN", "x")
    assert run_hook(json.dumps(call("ssh box make"))).returncode == 2
    assert guard.verdict(call("LOOP_HOST_RUN=placed ssh box make"))[0] == 2


def test_nested_shells_stop_at_a_depth() -> None:
    inner = "make"
    for _ in range(guard.SHELL_DEPTH + 1):
        inner = f"sh -c {json.dumps(inner)}"
    assert guard.verdict(call(f"ssh box {json.dumps(inner)}")) == (0, "")


def test_the_hook_process_refuses_with_exit_2_and_the_reason_on_stderr() -> None:
    done = run_hook(json.dumps(call("ssh box 'cd repo && git push'")))
    assert done.returncode == 2 and done.stdout == ""
    assert done.stderr.startswith("Remote run refused: `cd repo && git push` over ssh to box")
    allowed = run_hook(json.dumps(call("ssh box tail -n 5 log")))
    assert allowed.returncode == 0 and allowed.stderr == ""


@pytest.mark.parametrize("stdin", ["", "not json", "[1, 2]", '{"tool_input": null}'])
def test_input_it_cant_read_is_allowed(stdin: str) -> None:
    done = run_hook(stdin)
    assert done.returncode == 0 and done.stderr == ""


def test_without_its_sibling_parser_the_hook_allows_everything(tmp_path: Path) -> None:
    lone = tmp_path / "remote_run_guard.py"
    lone.write_text(SCRIPT.read_text())
    done = subprocess.run(
        [sys.executable, str(lone)],
        input=json.dumps(call("ssh box make")),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0


def test_the_pack_registers_it_on_bash_beside_the_heavy_run_guard() -> None:
    hooks = json.loads((HOOKS / "hooks-claude.json").read_text())
    (group,) = hooks["hooks"]["PreToolUse"]
    assert group["matcher"] == "Bash"
    commands = [hook["command"] for hook in group["hooks"]]
    assert 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/remote_run_guard.py"' in commands
    assert 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/heavy_run_guard.py"' in commands


def test_the_hook_parses_on_the_oldest_python3_a_consumer_has() -> None:
    """It runs on the consumer's own ``python3`` (macOS ships 3.9), not this repo's 3.14."""
    import ast

    ast.parse(SCRIPT.read_text(), feature_version=(3, 9))
