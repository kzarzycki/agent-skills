"""scripts/spec_gate.py: a PR lands only when every issue it closes is ready-for-agent, with labels from the project's tracker file."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

SPEC = importlib.util.spec_from_file_location(
    "spec_gate",
    Path(__file__).resolve().parents[1]
    / "skills"
    / "engineering-loop"
    / "scripts"
    / "spec_gate.py",
)
assert SPEC and SPEC.loader
spec_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(spec_gate)

PROJECT = Path(__file__).resolve().parent / "fixtures" / "loop-project"
TRACKER = (PROJECT / "docs" / "agents" / "issue-tracker.md").read_text()
COMPONENTS = spec_gate.listed(TRACKER, "Components")
CATEGORIES = spec_gate.CATEGORIES | spec_gate.listed(TRACKER, "Extra categories")


def problems(issues: list[dict[str, Any]]) -> list[str]:
    return spec_gate.problems(issues, COMPONENTS, CATEGORIES)


def issue(number: int, *labels: str) -> dict[str, Any]:
    return {"number": number, "labels": {"nodes": [{"name": name} for name in labels]}}


def specced(number: int, *labels: str) -> dict[str, Any]:
    return issue(number, "ready-for-agent", "web", "size:S", *labels)


def test_the_tracker_file_lists_components_and_extra_categories_from_their_own_sections() -> None:
    assert (COMPONENTS, CATEGORIES - spec_gate.CATEGORIES) == ({"agents", "api", "web"}, {"ops"})
    assert spec_gate.listed(TRACKER, "Sizes") == set()  # no such section


def test_a_pr_that_closes_no_issue_skipped_the_spec() -> None:
    assert problems([]) == [
        "the PR closes no issue: it needs a `Closes #<spec>` line for a ready-for-agent spec"
    ]


def test_an_intent_or_a_parked_issue_is_named() -> None:
    found = problems(
        [
            specced(1, "bug"),
            issue(2, "chore", "agents", "size:XS"),
            issue(3, "needs-owner", "bug", "api", "size:M"),
        ]
    )
    assert found == [
        "#2 is not ready-for-agent: triage and spec it first",
        "#3 is not ready-for-agent: triage and spec it first",
    ]


def test_every_closing_issue_specced_lands() -> None:
    assert problems([specced(1, "ops", "triaged-by-bot"), specced(2, "bug", "api")]) == []


def test_a_specced_issue_without_exactly_one_category_is_named() -> None:
    found = problems([specced(1), specced(2, "bug", "chore")])
    categories = "bug, chore, documentation, enhancement, ops"
    assert found == [
        f"#1 needs exactly one category label ({categories}), has 0",
        f"#2 needs exactly one category label ({categories}), has 2",
    ]


def test_a_wayfinder_ticket_needs_only_its_state() -> None:
    assert problems([issue(58, "wayfinder:task", "ready-for-agent")]) == []
    assert problems([issue(58, "wayfinder:task")]) == [
        "#58 is not ready-for-agent: triage and spec it first"
    ]


def test_a_specced_issue_without_a_component_or_exactly_one_size_is_named() -> None:
    found = problems([issue(1, "ready-for-agent", "bug"), specced(2, "bug", "size:M")])
    sizes = "size:L, size:M, size:S, size:XL, size:XS"
    assert found == [
        f"#1 needs exactly one size label ({sizes}), has 0",
        "#1 needs a component label (agents, api, web)",
        f"#2 needs exactly one size label ({sizes}), has 2",
    ]


def test_a_tracker_file_without_components_says_so() -> None:
    assert (
        spec_gate.problems([specced(1, "bug")], set())[-1]
        == "#1 needs a component label (docs/agents/issue-tracker.md lists none)"
    )


@pytest.mark.parametrize(
    ("body", "numbers"),
    [
        ("Closes #549", [549]),
        ("Closes #556.\n\n## Summary", [556]),
        ("fixes #1, Resolved: #2 and CLOSE #3; closes #1\tclosed #4", [1, 2, 3, 4]),
        ("An example: `Closes #5`, <!-- Closes #6 -->\n```\nFixes #7\n```\nCloses #8", [8]),
        ("## Fixes\n\n#12 and closes\n#13; closes #14x", []),
        (
            "- step:\n  ```\n  Fixes #7\n  ```\n> ```\n> Fixes #9\n> ```\n```\nx ``` y\nFixes #10\n```\nCloses #8",
            [8],
        ),
        ("Use ``` inline.\nCloses #15\n```\ncode\n```\nRun `a` then\nFixes:\t#16\n`b`", [15, 16]),
        ("Fix #7\nfixed #8\nresolve #9\nresolves #10", [7, 8, 9, 10]),
        ("", []),
        ("See #12; follows #13. Discloses #14, prefix #15, closes owner/repo#16, closes#17", []),
    ],
)
def test_the_body_names_its_closing_issues(body: str, numbers: list[int]) -> None:
    assert spec_gate.named(body) == numbers


def test_a_closing_line_with_no_such_issue_fails_with_the_reason(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refused(_pr: int) -> list[dict[str, Any]]:
        raise subprocess.CalledProcessError(
            1,
            "gh",
            stderr="gh: Could not resolve to an issue or pull request with the number of 9.\n",
        )

    monkeypatch.setattr(spec_gate, "closing_issues", refused)
    monkeypatch.chdir(PROJECT)
    assert (spec_gate.main(["1"]), capsys.readouterr().out) == (
        1,
        "gh: Could not resolve to an issue or pull request with the number of 9.\n",
    )


def test_run_outside_a_repo_with_a_tracker_file_fails_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert (spec_gate.main(["1"]), capsys.readouterr().out) == (
        1,
        "docs/agents/issue-tracker.md: No such file or directory: run from the repo root\n",
    )


def test_main_reads_the_projects_own_components_and_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tracker = tmp_path / "docs" / "agents" / "issue-tracker.md"
    tracker.parent.mkdir(parents=True)
    tracker.write_text(
        "## Components\n\n- `billing`: invoices.\n\n## Extra categories\n\n- `research`\n"
    )
    closing = [issue(1, "ready-for-agent", "billing", "research", "size:S")]
    monkeypatch.setattr(spec_gate, "closing_issues", lambda _pr: closing)
    monkeypatch.chdir(tmp_path)
    assert (spec_gate.main(["1"]), capsys.readouterr().out) == (0, "")
