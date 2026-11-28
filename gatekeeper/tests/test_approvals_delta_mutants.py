"""A delta pass mutates only the mutants the previous pass's findings listed (R2), and the brief counts how often a
finding has come back and prints the design-note requirement for one reported twice (R4); #3032 of #3029."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from approvals_harness import BASE, HEAD, approvals, pull
from test_approvals import LOOP, verdict_on

CRITERIA = "- A retry never double-charges: Before merge line 1, its check."


def delta(findings: str, verdict: str, extra: str = "") -> str:
    return (
        "Verifier: claude, pass 3\n\n## Criteria\n\n"
        f"{CRITERIA}\n\n## Correctness\n\n{findings}\n{extra}Head: {HEAD}\nVERDICT: {verdict}\n"
        "SATISFIED: no\nRisk: low — a test fixture\n"
    )


def survivor(mutant: str, severity: str = "major") -> str:
    return f"### F1 ({severity}) app.py:3: a surviving mutant\n\nIt survives.\nMutant: {mutant}\nBreaks: Acceptance line 1\nOrigin: new\n"


PRIOR = "Verifier: claude, pass 2\n\n## Correctness\n\n### F1 (major) app.py:3: x\n\nMutants: `a > b` -> `a >= b`; drop the guard\n"


def test_a_major_whose_mutant_is_not_on_the_prior_reports_list_is_flagged_and_a_listed_one_is_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prior, report = tmp_path / "prior.md", tmp_path / "report.md"
    prior.write_text(PRIOR)
    report.write_text(delta(survivor("drop the guard"), "0 blocker, 1 major, 0 minor"))
    assert approvals.main(["report", str(report), "--prior", str(prior)]) == 0
    report.write_text(delta(survivor("rename the helper"), "0 blocker, 1 major, 0 minor"))
    assert approvals.main(["report", str(report), "--prior", str(prior)]) == 1
    out = capsys.readouterr().out
    assert "names the mutant `rename the helper`" in out and "a new survivor is a minor" in out
    # a new survivor written as a minor, and a report with no prior to compare, are read as before
    report.write_text(delta(survivor("rename the helper", "minor"), "0 blocker, 0 major, 1 minor"))
    assert approvals.main(["report", str(report), "--prior", str(prior)]) == 0
    report.write_text(delta(survivor("rename the helper"), "0 blocker, 1 major, 0 minor"))
    assert approvals.main(["report", str(report)]) == 0


def test_the_mutants_a_finding_lists_are_read_from_its_mutants_lines() -> None:
    assert approvals.mutants_listed([PRIOR, "no list here", "Mutants: x"]) == [
        "a > b` -> `a >= b",
        "drop the guard",
        "x",
    ]


def finding(pass_: int, name: str, title: str, extra: str = "") -> dict[str, Any]:
    return {
        "body": f"**Verifier (codex), pass {pass_} · {name}** (major): {title}\n\nit fails\n{extra}"
    }


def briefed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    notes: list[dict[str, Any]],
) -> str:
    monkeypatch.chdir(tmp_path)
    earlier = "c" * 40
    reviews = tuple(verdict_on(earlier, heading=f"Verifier (codex), pass {n}") for n in (1, 2))
    pr = pull(body="Closes #12.\n", reviews=reviews)
    pr["reviewThreads"] = {
        "totalCount": 1,
        "nodes": [{"isResolved": False, "comments": {"nodes": notes}}],
    }
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.setattr(approvals, "merge_base", lambda base, head: BASE)
    monkeypatch.setattr(approvals, "project", lambda: (None, LOOP))
    assert approvals.main(["brief", "7"]) == 0
    return capsys.readouterr().out


def test_the_brief_carries_the_prior_findings_mutants_to_kill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = briefed(
        monkeypatch,
        tmp_path,
        capsys,
        [finding(2, "F1", "a gap", "Mutants: drop the guard; flip the sign\n")],
    )
    assert "- Mutants to kill, pass 2: drop the guard; flip the sign\n" in out


def test_a_finding_reported_twice_prints_the_design_note_requirement_with_its_repeat_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    notes = [
        finding(1, "F1", "a lock is taken twice"),
        finding(2, "F1", "A lock is taken twice"),
        finding(2, "F2", "a new gap", "Origin: new\n"),
    ]
    out = briefed(monkeypatch, tmp_path, capsys, notes)
    assert "Repeat count: 2" in out and "Repeat count: 1" in out
    assert "- Repeated findings: F1 (reported 2 times). The fix needs one design note" in out
    assert "or the lead's `Cap:` exit" in out
    # linked by the origin line when the title was reworded
    notes[1] = finding(2, "F1", "the lock again", "Origin: prior F1 not fixed\n")
    assert "- Repeated findings: F1 (reported 2 times)" in briefed(
        monkeypatch, tmp_path, capsys, notes
    )


def test_a_brief_with_no_repeated_finding_prints_no_design_note_requirement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = briefed(monkeypatch, tmp_path, capsys, [finding(2, "F1", "only once")])
    assert "Repeated findings" not in out and "Repeat count: 1" in out


def test_verdict_checks_a_delta_pass_s_mutants_against_the_posted_previous_findings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pr = pull(
        body="Closes #12.\n", reviews=(verdict_on("c" * 40, heading="Verifier (codex), pass 2"),)
    )
    pr["reviewThreads"] = {
        "totalCount": 1,
        "nodes": [
            {
                "isResolved": False,
                "comments": {"nodes": [finding(2, "F1", "a gap", "Mutants: drop the guard\n")]},
            }
        ],
    }
    posted: list[Any] = []
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.setattr(approvals, "diff_lines", lambda _base, _head: {"app.py": [3]})
    monkeypatch.setattr(approvals, "post_review", lambda n, review: posted.append(review))
    monkeypatch.setattr(approvals, "hand_over", lambda _n: None)
    report = tmp_path / "report.md"
    report.write_text(delta(survivor("rename the helper"), "0 blocker, 1 major, 0 minor"))
    assert approvals.main(["verdict", "7", str(report)]) == 1
    assert "a new survivor is a minor" in capsys.readouterr().out and not posted
    report.write_text(delta(survivor("drop the guard"), "0 blocker, 1 major, 0 minor"))
    assert approvals.main(["verdict", "7", str(report)]) == 0 and posted
