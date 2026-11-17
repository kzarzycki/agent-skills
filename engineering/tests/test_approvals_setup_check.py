"""approvals.py check setup: a consumer's gate fails where a loop step would exit non-zero after a pack upgrade."""

from __future__ import annotations

from pathlib import Path

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

BULLETS = "# Gatekeeper\n\n## Policy\n\n- spec: auto unless risk\n- merge: auto unless risk\n"
FENCED = gatekeeper_md("spec:\n  auto: true\n")
UV_TASK = '[tasks."loop:approvals"]\nrun = "uv run .agents/skills/engineering-loop/scripts/approvals.py check merge"\n'
BARE_TASK = UV_TASK.replace("uv run", "python3")
WORKFLOW = """name: approvals
on: pull_request
jobs:
  approvals:
    runs-on: ubuntu-latest
    steps:
      - uses: jdx/mise-action@v4
        with:
          %s
      - run: mise run loop:approvals merge 1
"""


@pytest.fixture(autouse=True)
def fresh() -> None:
    for cached in (approvals.default_base, approvals.unbased, approvals.differs):
        if clear := getattr(cached, "cache_clear", None):
            clear()


def repo_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **files: str) -> Path:
    """A checkout with no origin (so its working tree is read) holding the files, named with `__` for `/`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git_in(repo, "init", "-q", "-b", "main")
    for name, text in files.items():
        path = repo / name.replace("__", "/").replace("_md", ".md").replace("_toml", ".toml")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    monkeypatch.chdir(repo)
    return repo


def test_a_bullet_policy_fails_the_check_and_names_the_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = repo_with(tmp_path, monkeypatch, docs__agents__gatekeeper_md=BULLETS, mise_toml=UV_TASK)
    with pytest.raises(approvals.Refused) as refused:
        approvals.setup()
    message = str(refused.value)
    assert "docs/agents/gatekeeper.md" in message and "fenced yaml block under ## Policy" in message
    assert "before the pin bump" in message
    (repo / "docs/agents/gatekeeper.md").write_text(FENCED)
    assert approvals.setup() == 0


def test_a_bare_python_task_fails_the_check_until_it_runs_with_uv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = repo_with(tmp_path, monkeypatch, docs__agents__gatekeeper_md=FENCED, mise_toml=BARE_TASK)
    assert approvals.setup() == 1
    assert "mise.toml:2" in capsys.readouterr().out
    (repo / "mise.toml").write_text(UV_TASK)
    assert approvals.setup() == 0


def test_a_workflow_that_installs_no_uv_fails_the_check_until_it_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = ".github/workflows/approvals.yml".replace("/", "__")
    repo = repo_with(
        tmp_path,
        monkeypatch,
        docs__agents__gatekeeper_md=FENCED,
        mise_toml=UV_TASK,
        **{flow: WORKFLOW % "install: false"},
    )
    assert approvals.setup() == 1
    assert "job `approvals`" in capsys.readouterr().out
    (repo / ".github/workflows/approvals.yml").write_text(WORKFLOW % "install_args: uv")
    assert approvals.setup() == 0
