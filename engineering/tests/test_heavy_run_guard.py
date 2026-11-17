"""The engineering pack's PreToolUse hook refuses a heavy test or check run on a host (#1233)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
SCRIPT = HOOKS / "heavy_run_guard.py"
spec = importlib.util.spec_from_file_location("heavy_run_guard", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

# a host session the cloud route can run from: an Omnigent server is configured
HOST = {"RUNNER_SERVER_URL": "http://127.0.0.1:1"}
HEAVY = [
    "pytest",
    "pytest -q",
    "pytest tests/",
    "pytest tests/test_a.py -n 4",
    "pytest tests/test_a.py -nauto",
    "pytest tests/test_a.py --numprocesses=4",
    "python -m pytest",
    "python3 -m pytest -x tests",
    "python3.14 -m pytest",
    "uv run pytest -q",
    "uv run --with pytest-xdist python -m pytest",
    ".venv/bin/pytest",
    "mise run check",
    "mise run check:lint",
    "mise run test",
    "mise run test-engineering-package",
    "make test",
    "make -j4 check",
    "npm test",
    "npm run test",
    "pnpm test",
    "yarn run test",
    "cargo test",
    "cargo test --workspace",
    "go test ./...",
    "tox",
    "tox -e py314",
    "nox -s tests",
    "gradle test",
    "./gradlew check",
    "./gradlew build",
    "mvn test",
    "./mvnw verify",
    "uv run engineering/skills/engineering-loop/scripts/approvals.py local-ci --run",
    "python3 approvals.py local-ci 12 --record",
    "uv run approvals.py affected-tests",
    # every segment of a chain, after its leading words
    "git fetch && pytest",
    "cd engineering && uv run pytest -q",
    "ruff check . ; pytest",
    "pytest | tail -5",
    "FOO=1 BAR=2 pytest",
    "timeout 600 pytest",
    "timeout -s KILL 600 mise run check",
    "nohup pytest > log 2>&1 &",
    "exec cargo test",
    "git status\npytest -q",
    "(cd x && pytest)",
]
LIGHT = [
    "pytest tests/test_a.py",
    "pytest -q tests/test_a.py::test_one",
    "pytest tests/test_a.py tests/test_b.py -k slow -x",
    "uv run pytest engineering/tests/test_heavy_run_guard.py -q",
    "python3 -m pytest tests/test_a.py > out.txt 2>&1",
    "git status",
    "git commit -m 'pytest everything'",
    "ruff check engineering",
    "mise run lint",
    "mise run vendor-engineering",
    "make lint",
    "npm install",
    "npm run build",
    "cargo build",
    "go build ./...",
    "approvals.py local-ci 12",
    "uv run approvals.py check build",
    "echo pytest",
    "grep -rn 'mise run check' docs",
    "cat > x.sh <<'EOF'\npytest\nmise run check\nEOF",
    "ls # pytest",
]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository that runs the loop with cloud workers: ``.git`` and a loop.md."""
    (tmp_path / ".git").mkdir()
    loop = tmp_path / "docs" / "agents" / "loop.md"
    loop.parent.mkdir(parents=True)
    loop.write_text("# Loop\n\nCloud worker: claude-cloud, gate test\n")
    return tmp_path


def call(command: str, cwd: Path) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


def refused(command: str, cwd: Path, env: dict[str, str] = HOST) -> str | None:
    """The refusal the hook gives, None when it allows the call (silently)."""
    code, line = guard.verdict(call(command, cwd), env)
    if code == 0:
        assert line == "", line
        return None
    assert code == 2
    return line


@pytest.mark.parametrize("command", HEAVY)
def test_a_heavy_command_on_a_host_is_refused_naming_its_cloud_run_call(
    repo: Path, command: str
) -> None:
    reason = refused(command, repo)
    assert reason is not None, command
    assert f"claude-cloud-run --checkout {repo} -- " in reason
    assert command.strip().split("\n")[0] in reason  # the exact command, in the call and fallback
    assert "LOOP_HOST_RUN=<reason>" in reason


@pytest.mark.parametrize("command", LIGHT)
def test_a_light_command_is_allowed(repo: Path, command: str) -> None:
    assert refused(command, repo) is None, command


@pytest.mark.parametrize(
    "command",
    [
        "LOOP_HOST_RUN=x pytest",
        "LOOP_HOST_RUN='claude-cloud-run failed: quota' mise run check",
        "LOOP_HOST_RUN=device pytest && cargo test",  # the whole command starts with it
        "git fetch && LOOP_HOST_RUN=x pytest",  # a segment prefixed with it
    ],
)
def test_the_host_fallback_prefix_allows_it(repo: Path, command: str) -> None:
    assert refused(command, repo) is None


def test_an_empty_fallback_reason_is_no_fallback(repo: Path) -> None:
    assert refused("LOOP_HOST_RUN= pytest", repo) is not None


def test_a_cloud_session_is_allowed(repo: Path) -> None:
    assert refused("pytest", repo, {**HOST, "CLAUDE_CODE_REMOTE": "true"}) is None
    assert refused("pytest", repo, {**HOST, "CLAUDE_CODE_REMOTE": "false"}) is not None


def test_a_repo_without_loop_md_or_with_host_workers_is_allowed(repo: Path) -> None:
    loop = repo / "docs" / "agents" / "loop.md"
    loop.write_text("# Loop\n\nCloud worker: none, the suite needs a device\n")
    assert refused("pytest", repo) is None
    loop.unlink()
    assert refused("pytest", repo) is None


def test_outside_any_repository_it_allows(tmp_path: Path) -> None:
    assert refused("pytest", tmp_path) is None


def test_it_finds_the_repo_from_the_calls_cwd_and_runs_the_cloud_call_from_there(
    repo: Path,
) -> None:
    sub = repo / "pkg" / "src"
    sub.mkdir(parents=True)
    reason = refused("pytest", sub)
    assert reason is not None and f"--checkout {repo} -- 'cd pkg/src && pytest'" in reason


def test_a_command_it_cannot_parse_is_allowed(repo: Path) -> None:
    for payload in ("not json", "[]", '{"tool_input": null}', '{"tool_input": {"command": 7}}'):
        done = run_hook(payload, repo)
        assert done.returncode == 0 and not done.stderr, payload
    done = run_hook(json.dumps(call("pytest 'unclosed", repo)), repo)
    assert done.returncode == 0 and not done.stderr


def run_hook(
    stdin: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin", **(env or {})},
        check=False,
    )


def test_the_hook_refuses_with_exit_2_and_the_reason_on_stderr(repo: Path) -> None:
    """Claude Code's PreToolUse contract: exit 2 blocks the call and shows stderr to the model."""
    done = run_hook(json.dumps(call("uv run pytest -q", repo)), repo, HOST)
    assert done.returncode == 2 and done.stdout == ""
    assert (
        "claude-cloud-run" in done.stderr
        and "LOOP_HOST_RUN=<reason> uv run pytest -q" in done.stderr
    )
    allowed = run_hook(json.dumps(call("git status", repo)), repo, HOST)
    assert allowed.returncode == 0 and allowed.stderr == ""
    cloud = run_hook(json.dumps(call("pytest", repo)), repo, {**HOST, "CLAUDE_CODE_REMOTE": "true"})
    assert cloud.returncode == 0 and cloud.stderr == ""


@pytest.mark.parametrize("command", ["pytest", "mise run check", "cd x && cargo test"])
def test_without_an_omnigent_server_a_heavy_run_stays_here_with_one_notice_line(
    repo: Path, command: str
) -> None:
    """Plain Claude Code (no RUNNER_SERVER_URL) can't take the cloud route, so nothing is blocked."""
    code, line = guard.verdict(call(command, repo), {})
    assert code == 0 and line == guard.NOTICE and "\n" not in line
    assert "stayed on this machine" in line and "SKILL.md, Cloud worker" in line
    assert guard.verdict(call(command, repo), {"RUNNER_SERVER_URL": ""})[0] == 0  # empty: unset
    done = run_hook(json.dumps(call(command, repo)), repo)  # the hook's own environment
    assert done.returncode == 0 and done.stderr == guard.NOTICE + "\n"


def test_without_an_omnigent_server_a_light_run_gets_no_notice(repo: Path) -> None:
    assert guard.verdict(call("git status", repo), {}) == (0, "")
    assert guard.verdict(call("LOOP_HOST_RUN=x pytest", repo), {}) == (0, "")


def test_the_pack_registers_the_hook_on_bash_for_claude() -> None:
    hooks = json.loads((HOOKS / "hooks-claude.json").read_text())
    (group,) = hooks["hooks"]["PreToolUse"]
    assert group["matcher"] == "Bash"
    (hook,) = group["hooks"]
    assert hook["command"] == 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/heavy_run_guard.py"'
    # no plugin.json "hooks" field: APM would then deploy the hook to every target, Codex too
    plugin = json.loads((HOOKS.parent / ".claude-plugin" / "plugin.json").read_text())
    assert "hooks" not in plugin
