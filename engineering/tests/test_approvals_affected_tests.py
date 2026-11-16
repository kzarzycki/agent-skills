"""approvals.py affected-tests: loop.md's `Affected tests:` line is the worker's gate on a draft head (#1174)."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    gatekeeper_md,
    git_in,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

# a selector: the tests a change affects since the base it reads from GATE_BASE (or the variable `Gate base:` names), none
# for a docs-only change; it logs what it selected and runs
SELECTOR = """import os, pathlib, subprocess, sys
var = sys.argv[1] if len(sys.argv) > 1 else "GATE_BASE"
changed = subprocess.run(["git", "diff", "--name-only", os.environ[var], "HEAD"], capture_output=True, text=True, check=True).stdout.split()
chosen = [f for f in changed if f.endswith(".py")]
log = pathlib.Path(__file__).parent / "ran.log"
log.open("a").write("selected " + (" ".join(chosen) or "nothing") + "\\n")
sys.exit(0)
"""

# a stand-in `mise` that logs its arguments and whether the base variable reached it
MISE = """#!/bin/sh
echo "mise $* base=${GATE_BASE:-unset}" >> "$(dirname "$0")/ran.log"
"""


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A clone of an origin holding `main`, on a branch of its own, with loop.md's text settable and a fake `mise`
    on the path. `ran()` lists what the selector and `mise` logged; `commit(path, text)` commits a file."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git_in(tmp_path, "clone", "-q", str(origin), str(repo))
    git_in(repo, "config", "user.email", "loop@example.com")
    git_in(repo, "config", "user.name", "loop")
    git_in(repo, "checkout", "-q", "-b", "main")
    (repo / "docs" / "agents").mkdir(parents=True)
    (repo / "app.py").write_text("value = 1\n")
    git_in(repo, "add", "-A")
    git_in(repo, "commit", "-qm", "base")
    git_in(repo, "push", "-q", "-u", "origin", "main")
    git_in(repo, "remote", "set-head", "origin", "main")
    git_in(repo, "checkout", "-q", "-b", "work")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "selector.py").write_text(SELECTOR)
    (tools / "mise").write_text(MISE)
    (tools / "mise").chmod((tools / "mise").stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("GATE_BASE", raising=False)
    monkeypatch.delenv("MY_BASE", raising=False)
    monkeypatch.setattr(approvals, "policy_base", lambda _root, _base=None: None)
    monkeypatch.chdir(repo)
    log = tools / "ran.log"

    def commit(path: str, text: str) -> None:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
        git_in(repo, "add", "-A")
        git_in(repo, "commit", "-qm", path)

    def set_loop(text: str) -> None:
        (repo / "docs" / "agents" / "loop.md").write_text(text)

    return {
        "commit": commit,
        "set_loop": set_loop,
        "ran": lambda: log.read_text().splitlines() if log.exists() else [],
        "selector": f"{sys.executable} {tools / 'selector.py'}",
    }


def test_a_docs_only_head_runs_no_tests_under_a_selector_that_returns_none(
    worker: dict[str, Any],
) -> None:
    worker["set_loop"](f"# Loop\n\nAffected tests: {worker['selector']}\n")
    worker["commit"]("docs/guide.md", "words\n")
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == ["selected nothing"]


def test_a_code_head_runs_the_selection_against_the_merge_base(worker: dict[str, Any]) -> None:
    worker["set_loop"](f"# Loop\n\nAffected tests: {worker['selector']}\n")
    worker["commit"]("app.py", "value = 2\n")
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == ["selected app.py"]


def test_the_base_goes_in_the_variable_the_gate_base_line_names(
    worker: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    worker["set_loop"](
        f"# Loop\n\nGate base: MY_BASE\n\nAffected tests: MY_BASE_SET=1 {worker['selector']} MY_BASE\n"
    )
    worker["commit"]("app.py", "value = 2\n")
    monkeypatch.setenv("GATE_BASE", "stale")  # not the project's variable: left as it is
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == ["selected app.py"]


def test_without_the_line_the_fallback_is_check_with_no_base_set(
    worker: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    worker["set_loop"]("# Loop\n\nNo selector here.\n")
    worker["commit"]("docs/guide.md", "words\n")
    monkeypatch.setenv("GATE_BASE", "abc")  # a caller's selection never leaks into the full run
    assert approvals.main(["affected-tests"]) == 0
    assert worker["ran"]() == ["mise run check base=unset"]


def test_a_selector_that_fails_fails_the_gate(worker: dict[str, Any]) -> None:
    worker["set_loop"](f"# Loop\n\nAffected tests: {sys.executable} -c 'raise SystemExit(3)'\n")
    assert approvals.main(["affected-tests"]) == 3


def test_land_and_local_ci_never_set_the_base_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate of `land` and `local-ci` runs the full selection: a base in the caller's environment is cleared when
    the project names it in `local_ci_env`, and never set by the gate itself; only a head proof's `env` takes it."""
    policy = approvals.Policy(gatekeeper_md("loop:\n  local_ci_env:\n    - GATE_BASE\n"))
    monkeypatch.setattr(approvals, "project", lambda: (None, policy))
    monkeypatch.setenv("GATE_BASE", "abc")
    command, _, sets = approvals.gate()
    assert "GATE_BASE" not in command and sets == {}
    assert "GATE_BASE" not in approvals.gate_env({"sets": sets})
    _, _, with_proof = approvals.gate(["GATE_BASE"])
    assert with_proof == {"GATE_BASE": "abc"}
