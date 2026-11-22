"""The engineering pack's PreToolUse hook refuses a heavy test or check run on a host (#1233)."""

import importlib.util
import json
import shlex
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
    "uv run gatekeeper/skills/gatekeeper/scripts/approvals.py local-ci --run",
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
    # a rerun of the last failures, which a cloud clone has no cache for, and xdist
    "pytest --lf",
    "pytest --ff tests/test_a.py",
    # wrappers, keywords and nested shells it sees through (#1234 verifier m2)
    "env FOO=1 pytest",
    "env -u HOME pytest",
    "time pytest",
    "time -p mise run check",
    "command pytest",
    "sudo pytest",
    "sudo -u ci cargo test",
    "uvx pytest",
    "uvx --from pytest pytest",
    "uv tool run pytest",
    "! pytest",
    "{ pytest; }",
    "if true; then pytest; fi",
    "while true; do pytest; done",
    "mise r check",
    "xargs pytest",
    "xargs -n 1 pytest",
    'bash -c "pytest"',
    "sh -c 'uv run pytest'",
    "zsh -lc 'cd x && pytest'",
    "bash -c \"sh -c 'pytest'\"",
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
    # a plugin option's value is no test path (#1234 verifier m1)
    "pytest tests/test_a.py --timeout 30",
    "pytest tests/test_a.py --log-cli-level INFO",
    "pytest tests/test_a.py --reruns 2",
    "pytest tests/test_a.py --html report.html",
    "pytest tests/test_a.py no-such-dir",
    # a wrapper or a shell string around a light run stays light
    "command -v pytest",
    "env pytest tests/test_a.py",
    "bash -c 'git status'",
    "sh -c 'pytest tests/test_a.py'",
    "bash -c",
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


def test_the_hook_parses_on_the_oldest_python3_a_consumer_has() -> None:
    """It runs on the consumer's own ``python3`` (macOS ships 3.9), not this repo's 3.14."""
    import ast

    ast.parse(SCRIPT.read_text(), feature_version=(3, 9))


def test_a_word_that_is_an_existing_directory_makes_a_pytest_run_heavy(repo: Path) -> None:
    (repo / "tests").mkdir()
    assert refused("pytest tests/test_a.py tests", repo) is not None
    assert refused("pytest tests/test_a.py --basetemp tests", repo) is None  # a value never counts


def test_a_last_failed_rerun_says_the_cloud_clone_has_no_cache(repo: Path) -> None:
    for command in ("pytest --lf", "pytest --ff tests/test_a.py", "pytest --last-failed"):
        reason = refused(command, repo)
        assert reason is not None and "no `.pytest_cache`" in reason, command
    assert "pytest_cache" not in (refused("pytest", repo) or "")


def loop_checkout(path: Path, loop: bool = True) -> Path:
    path.mkdir(parents=True)
    (path / ".git").mkdir()
    if loop:
        (path / "docs" / "agents").mkdir(parents=True)
        (path / "docs" / "agents" / "loop.md").write_text("Cloud worker: claude-cloud\n")
    return path


def test_a_cd_into_another_checkout_is_judged_and_run_there(repo: Path, tmp_path: Path) -> None:
    """The verifier's M1: the cd's target picks the repo for both the loop.md check and --checkout."""
    plain = loop_checkout(tmp_path / "plain", loop=False)
    assert refused(f"cd {plain} && uv run pytest", repo) is None
    other = loop_checkout(tmp_path / "other")
    reason = refused(f"cd {other} && uv run pytest", repo)
    assert reason is not None and f"--checkout {other} -- 'uv run pytest'" in reason
    (other / "pkg").mkdir()
    reason = refused(f"cd {other}/pkg && pytest", repo)
    assert reason is not None and f"--checkout {other} -- 'cd pkg && pytest'" in reason
    # from outside any loop repo, a cd into one is refused
    assert refused(f"cd {other} && pytest", plain) is not None
    # a relative cd into a linked worktree (a .git file) runs on that worktree, with no cd
    tree = repo / ".worktrees" / "pr-7"
    tree.mkdir(parents=True)
    (tree / ".git").write_text("gitdir: elsewhere\n")
    (tree / "docs" / "agents").mkdir(parents=True)
    (tree / "docs" / "agents" / "loop.md").write_text("Cloud worker: claude-cloud\n")
    reason = refused("cd .worktrees/pr-7 && mise run check", repo)
    assert reason is not None and f"--checkout {tree} -- 'mise run check'" in reason
    # a cd into the checkout's own root goes from the call, as the session runs there
    reason = refused(f"cd {repo} && pytest", repo / "pkg")
    assert reason is not None and f"--checkout {repo} -- pytest" in reason


def test_a_cd_it_cannot_follow_allows_what_comes_after(repo: Path) -> None:
    for command in ("cd $WORK && pytest", "cd - && pytest", "cd && pytest", "cd `pwd` && pytest"):
        assert refused(command, repo) is None, command


def suggested(reason: str | None) -> tuple[str, str]:
    """The ``--checkout`` and the command of the refusal's ``claude-cloud-run`` call."""
    assert reason is not None
    line = next(x for x in reason.splitlines() if "claude-cloud-run --checkout" in x)
    words = shlex.split(line.strip())
    return words[words.index("--checkout") + 1], words[words.index("--") + 1]


@pytest.mark.parametrize(
    ("command", "where", "run"),
    [
        ("git pull && cd {other} && pytest", "other", "git pull && pytest"),
        (
            "git fetch && cd .worktrees/pr-7 && mise run check",
            "tree",
            "git fetch && mise run check",
        ),
        ("bash -c 'cd {other} && uv run pytest'", "other", "bash -c 'uv run pytest'"),
        ("cd {other} && git pull && cd pkg && pytest", "other", "git pull && cd pkg && pytest"),
        ("git pull && cd {other}/pkg && pytest", "other", "git pull && cd pkg && pytest"),
        ("cd {other}/pkg && cd sub && pytest", "other", "cd pkg && cd sub && pytest"),
        ("sh -c 'cd {other} && cd pkg && pytest'", "other", "sh -c 'cd pkg && pytest'"),
    ],
)
def test_every_cd_of_the_suggested_command_runs_inside_the_cloud_clone(
    repo: Path, tmp_path: Path, command: str, where: str, run: str
) -> None:
    """The verifier's pass-2 M1: a cd anywhere in the chain, or in a sh -c string, names a host path
    the clone lacks, so the call gets it relative to the checkout, or without it on the root."""
    other = loop_checkout(tmp_path / "other")
    tree = repo / ".worktrees" / "pr-7"
    tree.mkdir(parents=True)
    (tree / ".git").write_text("gitdir: elsewhere\n")
    (tree / "docs" / "agents").mkdir(parents=True)
    (tree / "docs" / "agents" / "loop.md").write_text("Cloud worker: claude-cloud\n")
    checkout, cloud = suggested(refused(command.format(other=other), repo))
    assert checkout == str(other if where == "other" else tree)
    assert cloud == run


@pytest.mark.parametrize(
    "command",
    [
        "cd {outside} && cd {other} && pytest",
        "cd {other} && cd .. && cd {other} && pytest",
        "bash -c 'cd {outside} && cd {other} && uv run pytest'",
    ],
)
def test_a_cd_outside_the_checkout_gets_the_fallback_alone(
    repo: Path, tmp_path: Path, command: str
) -> None:
    """No call is suggested that would fail on its cd and read as the suite failing."""
    other = loop_checkout(tmp_path / "other")
    command = command.format(other=other, outside=tmp_path.parent)
    reason = refused(command, repo)
    assert reason is not None and "claude-cloud-run --checkout" not in reason
    assert f"goes outside {other}" in reason
    assert reason.endswith(f"LOOP_HOST_RUN=<reason> {command}")


@pytest.mark.parametrize(
    ("command", "run"),
    [
        # forms the rewrite does not parse: the fallback alone (None)
        ("cd -P {repo}/sub && pytest", None),
        ("cd -- {repo}/sub && pytest", None),
        ("pushd {repo}/sub >/dev/null && pytest; popd", None),
        ("pushd sub && pytest; popd", None),
        ("builtin cd {repo}/sub && pytest", None),
        ("command cd {repo}/sub && pytest", None),
        ("make -C {repo}/sub test", None),
        ("cd -P sub && pytest", None),
        # a cd in a ( … ) group does not persist, so a later cd can't be placed
        ("(cd a/sub && ls); cd a && pytest", None),
        # the plain forms keep their rewrite
        ("cd {repo}/sub && pytest", "cd sub && pytest"),
        ("(cd sub && pytest)", "(cd sub && pytest)"),
        ("git pull && cd {repo} && pytest", "git pull && pytest"),
    ],
)
def test_a_suggested_call_never_names_a_host_directory(
    repo: Path, command: str, run: str | None
) -> None:
    """The verifier's pass-3 M2 and m1: whatever form changes directory, the suggested call holds
    no host path the cloud clone lacks; a form it can't place gets the fallback alone."""
    command = command.format(repo=repo)
    reason = refused(command, repo)
    assert reason is not None
    if run is None:
        assert "claude-cloud-run --checkout" not in reason
        assert reason.endswith(f"LOOP_HOST_RUN=<reason> {command}")
        return
    checkout, cloud = suggested(reason)
    assert checkout == str(repo) and cloud == run and str(repo) not in cloud
