"""The cap binds (R3): `brief` starts no pass past the cap's one scoped pass without a `Cap:` line; a verdict with an unrun
sibling on a major needs the budget line's reason (R7); #3033 of #3029."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import BASE, HEAD, LOOP, approvals, pull
from test_approvals import verdict_on

CAP = approvals.cap(LOOP)


def briefing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, last: int, body: str
) -> tuple[int, str]:
    monkeypatch.chdir(tmp_path)
    reviews = tuple(
        verdict_on("c" * 40, heading=f"Verifier (codex), pass {n}") for n in range(1, last + 1)
    )
    pr = pull(body=body, reviews=reviews)
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.setattr(approvals, "merge_base", lambda base, head: BASE)
    monkeypatch.setattr(approvals, "project", lambda: (None, LOOP))
    return approvals.main(["brief", "7"]), ""


def test_a_pass_5_start_is_refused_with_no_cap_line_and_allowed_with_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert CAP == 3
    assert briefing(monkeypatch, tmp_path, CAP + 1, "Closes #12.\n")[0] == 1
    assert "pass 5 is past the cap (3)" in capsys.readouterr().out
    assert briefing(monkeypatch, tmp_path, CAP + 1, "Closes #12.\n\nCap: #99\n")[0] == 0
    assert "Review PR #7 as the verifier, pass 5" in capsys.readouterr().out


@pytest.mark.parametrize("last", [0, CAP - 1, CAP])
def test_the_passes_up_to_the_one_past_the_cap_start_with_no_cap_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, last: int
) -> None:
    assert briefing(monkeypatch, tmp_path, last, "Closes #12.\n")[0] == 0


def test_a_quoted_cap_line_is_an_example_and_decides_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert briefing(monkeypatch, tmp_path, CAP + 1, "Closes #12.\n\n> Cap: #99\n")[0] == 1


CRITERIA = "- A retry never double-charges: Before merge line 1, its check."


def report(sibling: str, extra: str = "") -> str:
    return (
        "Verifier: claude, pass 1\n\n## Criteria\n\n"
        f"{CRITERIA}\n\n## Correctness\n\n### F1 (major) app.py:3: a gap\n\nIt fails.\n{sibling}\n\n"
        f"{extra}Head: {HEAD}\nVERDICT: 0 blocker, 1 major, 0 minor\nSATISFIED: no\nRisk: low — a fixture\n"
    )


@pytest.mark.parametrize(
    ("sibling", "extra", "refused"),
    [
        ("Sibling: the empty input: not run", "", True),
        ("Siblings: the empty input: not run", "", True),
        ("Sibling: the empty input: not run", "Budget: stopped at 60 tool calls\n", False),
        ("Sibling: the empty input: fine", "", False),
        ("Sibling: the empty input: failing (exit 1)", "", False),
    ],
)
def test_a_major_with_a_sibling_not_run_fails_the_parser_unless_the_budget_line_says_why(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sibling: str,
    extra: str,
    refused: bool,
) -> None:
    path = tmp_path / "report.md"
    path.write_text(report(sibling, extra))
    assert approvals.main(["report", str(path)]) == int(refused)
    assert ("sibling `not run`" in capsys.readouterr().out) == refused


def test_a_minor_with_a_sibling_not_run_is_read_as_before(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text(
        report("Sibling: the empty input: not run")
        .replace("(major)", "(minor)")
        .replace("0 blocker, 1 major, 0 minor", "0 blocker, 0 major, 1 minor")
    )
    assert approvals.main(["report", str(path)]) == 0


def test_verifier_md_carries_the_edge_input_checklist_line_and_the_sibling_rule() -> None:
    role = (
        Path(__file__).resolve().parents[2] / "loop/skills/engineering-loop/verifier.md"
    ).read_text()
    assert "edge inputs" in role and "parser or settings loader" in role
    assert "Sibling: <case>: failing (evidence)|fine|not run" in role
