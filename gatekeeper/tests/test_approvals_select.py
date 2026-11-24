"""approvals.py affected-tests: gatekeeper.md's `select` cuts the narrowed gate by build input (#1631)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import approvals, gatekeeper_md, git_in

# the project's `Affected tests:` command: it logs that it ran, so a test sees whether the cut let it through
SELECTOR = """import pathlib, sys
(pathlib.Path(__file__).parent / "ran.log").open("a").write("selector\\n")
"""

# a `checks` command: it logs its name, and exits with the code its second argument gives
CHECK = """import pathlib, sys
(pathlib.Path(__file__).parent / "ran.log").open("a").write(sys.argv[1] + "\\n")
sys.exit(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
"""

SELECT = """select:
  build_inputs:
    - src/*
    - package.json
  checks:
    - paths: [apm.yml, apm.lock.yaml, .agents/skills/*, .claude/skills/*]
      command: {check} agent-sync
    - paths: [scripts/release.sh]
      command: {check} release {release_exit}
"""


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A clone on a branch of its own whose base holds loop.md's `Affected tests:` line and gatekeeper.md with the
    policy `start(policy)` gives; `commit(path)` commits a file on the branch, `ran()` lists what ran."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "selector.py").write_text(SELECTOR)
    (tools / "check.py").write_text(CHECK)
    log = tools / "ran.log"
    check = f"{sys.executable} {tools / 'check.py'}"
    monkeypatch.delenv("GATE_BASE", raising=False)
    monkeypatch.setenv(approvals.WORKING_TREE_POLICY, "1")
    monkeypatch.setattr(approvals, "open_pulls", list)

    def start(policy: str | None, release_exit: int = 0) -> None:
        git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git_in(tmp_path, "clone", "-q", str(origin), str(repo))
        git_in(repo, "config", "user.email", "loop@example.com")
        git_in(repo, "config", "user.name", "loop")
        git_in(repo, "checkout", "-q", "-b", "main")
        agents = repo / "docs" / "agents"
        agents.mkdir(parents=True)
        (agents / "loop.md").write_text(
            f"# Loop\n\nAffected tests: {sys.executable} {tools / 'selector.py'}\n"
        )
        if policy is not None:
            (agents / "gatekeeper.md").write_text(
                gatekeeper_md(policy.format(check=check, release_exit=release_exit))
            )
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("value = 1\n")
        git_in(repo, "add", "-A")
        git_in(repo, "commit", "-qm", "base")
        git_in(repo, "push", "-q", "-u", "origin", "main")
        git_in(repo, "remote", "set-head", "origin", "main")
        git_in(repo, "checkout", "-q", "-b", "work")
        monkeypatch.chdir(repo)

    def commit(*paths: str) -> None:
        for path in paths:
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            target = (
                repo / path
            )  # appended to, so a changed loop.md keeps its `Affected tests:` line
            target.write_text((target.read_text() if target.exists() else "") + f"changed {path}\n")
        git_in(repo, "add", "-A")
        git_in(repo, "commit", "-qm", "change")

    return {
        "start": start,
        "commit": commit,
        "ran": lambda: log.read_text().splitlines() if log.exists() else [],
    }


def test_a_docs_only_change_runs_nothing(worker: dict[str, Any], capsys: Any) -> None:
    worker["start"](SELECT)
    worker["commit"]("docs/guide.md", "README.md")
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == []
    assert "no build input changed and no check applies" in capsys.readouterr().err


def test_a_pack_bump_runs_only_its_check(worker: dict[str, Any]) -> None:
    worker["start"](SELECT)
    worker["commit"](
        "apm.yml", "apm.lock.yaml", ".claude/skills/demo/SKILL.md", ".agents/skills/x/a.py"
    )
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == ["agent-sync"]


def test_a_failing_check_fails_the_run(worker: dict[str, Any]) -> None:
    worker["start"](SELECT, release_exit=3)
    worker["commit"]("scripts/release.sh", "apm.yml")
    assert approvals.main(["affected-tests"]) == 3
    assert worker["ran"]() == ["agent-sync", "release"]  # in the order of the files git lists


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",  # a declared build input
        "package.json",
        "Makefile",  # in neither list: unclear, so it tests
        ".github/workflows/ci.yml",
        "docs/agents/gatekeeper.md",  # the selection's own policy
        "docs/agents/loop.md",
    ],
)
def test_a_build_input_or_an_unclear_path_runs_the_selector(
    worker: dict[str, Any], path: str
) -> None:
    worker["start"](SELECT)
    worker["commit"]("docs/guide.md", path)
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == ["selector"]


def test_a_build_input_under_a_non_product_glob_still_tests(worker: dict[str, Any]) -> None:
    """build_inputs win over the pack's non-product set: a project whose product is markdown declares it."""
    worker["start"](SELECT.replace("    - package.json\n", "    - package.json\n    - content/*\n"))
    worker["commit"]("content/post.md")
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == ["selector"]


def test_without_select_a_docs_change_runs_the_selector_as_before(worker: dict[str, Any]) -> None:
    worker["start"](None)
    worker["commit"]("docs/guide.md")
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == ["selector"]


def test_classify_names_inputs_and_dedupes_checks() -> None:
    select = {
        "build_inputs": ["src/*"],
        "checks": [{"paths": ["apm.yml", ".claude/*"], "command": "mise run agent-sync --frozen"}],
    }
    assert approvals.classify(["apm.yml", ".claude/skills/a/SKILL.md", "docs/x.md"], select) == (
        [],
        ["mise run agent-sync --frozen"],
    )
    assert approvals.classify(["src/a.py", "tools/x.py"], select) == (
        ["src/a.py", "tools/x.py"],
        [],
    )
    assert approvals.classify(["docs/x.md"], {}) == (["docs/x.md"], [])


def test_select_without_build_inputs_cuts_nothing_and_keeps_unkeyed() -> None:
    """`select.unkeyed` (#2183) shares the section: without `build_inputs` every file is a build input, as before."""
    policy = approvals.Policy(gatekeeper_md("select:\n  unkeyed: [lint]\n"))
    select = approvals.settings(policy)["select"]
    assert select == {"unkeyed": ["lint"]}
    assert approvals.classify(["docs/x.md", "apm.yml"], select) == (["docs/x.md", "apm.yml"], [])
    both = approvals.Policy(gatekeeper_md("select:\n  build_inputs: [src/*]\n  unkeyed: [lint]\n"))
    assert approvals.settings(both)["select"] == {"build_inputs": ["src/*"], "unkeyed": ["lint"]}


def base_of_work() -> str:
    return git_in(Path.cwd(), "merge-base", "origin/main", "HEAD").strip()


def test_the_narrowed_gate_of_a_pack_bump_runs_and_records_only_its_check(
    worker: dict[str, Any],
) -> None:
    worker["start"](SELECT)
    worker["commit"]("apm.yml", ".claude/skills/demo/SKILL.md")
    base = base_of_work()
    with approvals.narrowed_to(base):
        command = approvals.narrowed_gate()[0]
    assert command.endswith(" agent-sync' (narrowed)") and "select.checks:" in command
    assert approvals.narrowed_base(command) == base
    assert approvals.main(["local-ci", "--record", "--base", base]) == 0
    assert worker["ran"]() == ["agent-sync"]
    # the pass is reused by tree: a second record runs nothing
    assert approvals.main(["local-ci", "--record", "--base", base]) == 0
    assert worker["ran"]() == ["agent-sync"]


def test_the_narrowed_gate_of_a_docs_change_runs_nothing_and_says_none(
    worker: dict[str, Any],
) -> None:
    worker["start"](SELECT)
    worker["commit"]("docs/guide.md")
    base = base_of_work()
    with approvals.narrowed_to(base):
        assert approvals.narrowed_gate()[0] == f"GATE_BASE={base} select.checks: none (narrowed)"
    assert approvals.main(["local-ci", "--record", "--base", base]) == 0
    assert worker["ran"]() == []


def test_the_narrowed_gate_of_a_build_input_runs_the_selector(worker: dict[str, Any]) -> None:
    worker["start"](SELECT)
    worker["commit"]("docs/guide.md", "src/app.py")
    base = base_of_work()
    with approvals.narrowed_to(base):
        assert "select.checks" not in approvals.narrowed_gate()[0]
    assert approvals.main(["local-ci", "--record", "--base", base]) == 0
    assert worker["ran"]() == ["selector"]
