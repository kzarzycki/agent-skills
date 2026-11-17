"""The engineering pack's host-run hook refuses a heavy test or check run in a host session of a
loop repo, naming cloud-run, and allows everything else (#1233)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
SCRIPT = HOOKS / "host_run.py"
_spec = importlib.util.spec_from_file_location("host_run", SCRIPT)
assert _spec and _spec.loader
host_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(host_run)

DETACHED = (
    "perl -MPOSIX=setsid -e 'fork and exit; setsid; exec @ARGV' sh -c 'echo $$ > tmp/loop/p;"
    ' echo "run $$" > tmp/loop/log; flock tmp/l sh -c "echo \\$\\$ > tmp/l; exec \\"\\$@\\"" sh'
    ' uv run approvals.py heavy pytest -q >> tmp/loop/log 2>&1; echo "exit $?" >> tmp/loop/log\''
    " >/dev/null 2>&1"
)

# The spec's table: each heavy form is refused on a host...
HEAVY = [
    "pytest",
    "pytest -q tests/",
    "pytest tests/test_a.py -n 4",
    "pytest tests/test_a.py -nauto",
    "pytest tests/test_a.py --numprocesses=2",
    "pytest -k slow",
    "python -m pytest",
    "python3 -m pytest -q engineering/tests",
    "uv run pytest",
    "uv run --with pytest-xdist python -m pytest tests/test_a.py -n 2",
    "mise run check",
    "mise run check:fast",
    "mise run test-engineering-package",
    "mise run lint ::: test",
    "mise r test",
    "make test",
    "make -C sub check",
    "npm test",
    "npm run test",
    "pnpm test",
    "yarn test",
    "yarn run test",
    "cargo test",
    "cargo +nightly test --workspace",
    "go test ./...",
    "tox -e py",
    "nox -s tests",
    "gradle test",
    "./gradlew check",
    "gradlew build",
    "./gradlew :app:test",
    "mvn test",
    "mvn clean verify",
    "./mvnw verify",
    "python3 engineering/skills/engineering-loop/scripts/approvals.py local-ci --run",
    "uv run x/approvals.py local-ci 12 --record",
    "uv run x/approvals.py affected-tests",
    # ...in every segment of a chain, after leading cd, env assignments, timeout, nohup and exec
    "cd sub && pytest",
    "git status; pytest",
    "ruff check . && FOO=1 BAR=2 timeout -s KILL 600 nohup exec pytest",
    "git fetch | uv run pytest",
    "env A=1 pytest",
    "bash -c 'pytest -q'",
    "pytest a.py\nmake test",
    "(cd sub && cargo test)",
    DETACHED,
]
# ...and each light one is allowed
LIGHT = [
    "pytest tests/test_a.py",
    "pytest tests/test_a.py::test_x -q",
    "uv run pytest -q tests/test_a.py -k foo -p no:cacheprovider",
    "pytest tests/test_a.py tests/test_b.py::T::test_y 2>&1 | tail -5",
    "git status",
    "git commit -m 'run pytest and make test'",
    "ruff check .",
    "uv run ruff format --check engineering/tests",
    "mise run lint",
    "mise run vendor-engineering-check",
    "make lint",
    "npm run build",
    "cargo build",
    "go vet ./...",
    "echo pytest",
    "grep -rn 'mise run check' docs",
    "cat > tmp/loop/brief.md <<'EOF'\npytest\nmise run check\nEOF",
    "python3 x/omnigent_agent.py cloud-run -- 'pytest -q'",
    "python3 x/approvals.py local-ci 12",
    "",
]


@pytest.fixture
def loop_repo(tmp_path: Path) -> Path:
    """A checkout that runs the loop with cloud workers: loop.md, no `Cloud worker: none`."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text("# Loop\n\nGate: mise run check\n")
    (tmp_path / "sub").mkdir()
    return tmp_path


def call(command: str, cwd: Path) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


@pytest.mark.parametrize("command", HEAVY)
def test_a_heavy_run_is_refused_on_a_host(loop_repo: Path, command: str) -> None:
    reason = host_run.verdict(call(command, loop_repo / "sub"), {}, SCRIPT)
    assert reason is not None, command
    assert "cloud-run --checkout" in reason and "LOOP_HOST_RUN=<reason>" in reason


@pytest.mark.parametrize("command", LIGHT)
def test_a_light_command_is_allowed(loop_repo: Path, command: str) -> None:
    assert host_run.verdict(call(command, loop_repo), {}, SCRIPT) is None


def test_the_refusal_names_cloud_run_for_that_exact_command_and_the_fallback(
    loop_repo: Path,
) -> None:
    command = "cd sub && uv run pytest -q -k 'a or b'"
    reason = host_run.verdict(call(command, loop_repo), {}, SCRIPT)
    assert reason
    launcher = HOOKS.parent / "skills" / "orchestrating-agents" / "scripts" / "omnigent_agent.py"
    assert (
        f"python3 {launcher} cloud-run --checkout {loop_repo} -- 'cd sub && uv run pytest -q -k '\"'\"'a or b'\"'\"''"
        in reason
    )
    assert f"LOOP_HOST_RUN=<reason> {command}" in reason
    assert "Where heavy steps run" in reason and "exits 125" in reason


@pytest.mark.parametrize("prefix", ["LOOP_HOST_RUN=x ", "  LOOP_HOST_RUN=placed "])
def test_the_host_run_prefix_allows(loop_repo: Path, prefix: str) -> None:
    assert host_run.verdict(call(prefix + "pytest", loop_repo), {}, SCRIPT) is None


def test_an_empty_prefix_does_not_allow(loop_repo: Path) -> None:
    assert host_run.verdict(call("LOOP_HOST_RUN= pytest", loop_repo), {}, SCRIPT)


def test_a_cloud_session_allows(loop_repo: Path) -> None:
    env = {"CLAUDE_CODE_REMOTE": "true"}
    assert host_run.verdict(call("pytest", loop_repo), env, SCRIPT) is None
    assert host_run.verdict(call("pytest", loop_repo), {"CLAUDE_CODE_REMOTE": "false"}, SCRIPT)


def test_a_repo_without_loop_md_allows(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert host_run.verdict(call("pytest", tmp_path), {}, SCRIPT) is None


@pytest.mark.parametrize(
    "line",
    ["Cloud worker: none", "Cloud worker: none, the suite needs a device", "cloud worker: NONE"],
)
def test_a_repo_with_host_workers_allows(loop_repo: Path, line: str) -> None:
    (loop_repo / "docs" / "agents" / "loop.md").write_text(f"# Loop\n\n{line}\n")
    assert host_run.verdict(call("pytest", loop_repo), {}, SCRIPT) is None


def test_a_cloud_worker_line_naming_an_agent_still_refuses(loop_repo: Path) -> None:
    (loop_repo / "docs" / "agents" / "loop.md").write_text(
        "Cloud worker: claude-cloud, gate check\n"
    )
    assert host_run.verdict(call("pytest", loop_repo), {}, SCRIPT)


@pytest.mark.parametrize("command", ['pytest "unclosed', "pytest 'a.py"])
def test_a_command_it_cannot_parse_is_allowed(loop_repo: Path, command: str) -> None:
    assert host_run.verdict(call(command, loop_repo), {}, SCRIPT) is None


def test_a_copy_deployed_for_codex_allows(loop_repo: Path, tmp_path: Path) -> None:
    hook = tmp_path / ".codex" / "hooks" / "engineering" / "hooks" / "host_run.py"
    assert host_run.verdict(call("pytest", loop_repo), {}, hook) is None


def run_hook(stdin: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **(env or {})},
        check=False,
        timeout=30,
    )


def test_the_hook_refuses_with_exit_2_and_the_reason_on_stderr(loop_repo: Path) -> None:
    done = run_hook(json.dumps(call("uv run pytest", loop_repo)))
    assert done.returncode == 2 and done.stdout == ""
    assert "cloud-run" in done.stderr and "LOOP_HOST_RUN=<reason> uv run pytest" in done.stderr


@pytest.mark.parametrize(
    "stdin", ["", "not json", "[1, 2]", '{"tool_input": {"command": 7}}', '{"tool_input": null}']
)
def test_the_hook_allows_input_it_cannot_read(stdin: str) -> None:
    done = run_hook(stdin)
    assert done.returncode == 0 and done.stderr == ""


def test_the_hook_allows_a_light_command_and_a_cloud_session(loop_repo: Path) -> None:
    assert run_hook(json.dumps(call("git status", loop_repo))).returncode == 0
    remote = run_hook(json.dumps(call("pytest", loop_repo)), {"CLAUDE_CODE_REMOTE": "true"})
    assert remote.returncode == 0 and remote.stderr == ""


def test_the_pack_registers_the_hook_on_bash_before_the_tool_runs() -> None:
    data = json.loads((HOOKS / "hooks.json").read_text())
    (group,) = data["hooks"]["PreToolUse"]
    assert group["matcher"] == "Bash"
    (hook,) = group["hooks"]
    assert hook["type"] == "command"
    assert hook["command"] == "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/host_run.py"
