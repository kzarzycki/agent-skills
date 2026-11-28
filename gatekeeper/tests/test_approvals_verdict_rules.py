"""approvals.py report: a major states what it breaks, a delta finding where it came from, and the counts decide
satisfaction (#3031: R1, R5, R6 of #3029)."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import HEAD, approvals

AT = "app.py:3"
CRITERIA = "- A retry never double-charges: Before merge line 1, its check."
STANDING = "Breaks: standing bar security"
PATH = "Path: POST /pay with a forged token skips the auth check and charges any account."


def report(
    findings: str = "",
    verdict: str = "0 blocker, 0 major, 0 minor",
    satisfied: str = "yes",
    number: int = 1,
    extra: str = "",
) -> str:
    return (
        f"Verifier: claude, pass {number}\n\n## Criteria\n\n{CRITERIA}\n\n## Correctness\n\n{findings}\n"
        f"{extra}Head: {HEAD}\nVERDICT: {verdict}\nSATISFIED: {satisfied}\nRisk: low — a test fixture\n"
    )


def facts(tmp_path: Path, text: str) -> dict:
    path = tmp_path / "report.md"
    path.write_text(text)
    return approvals.report_facts(path)


def refused(tmp_path: Path, text: str, capsys: pytest.CaptureFixture[str]) -> str:
    path = tmp_path / "report.md"
    path.write_text(text)
    assert approvals.main(["report", str(path)]) == 1
    return capsys.readouterr().out


def finding(severity: str, *lines: str) -> str:
    return f"### F1 ({severity}) {AT}: a finding\n\nIt fails.\n" + "\n".join(lines) + "\n"


def one(severity: str) -> str:
    return "0 blocker, 1 major, 0 minor" if severity == "major" else "0 blocker, 0 major, 1 minor"


@pytest.mark.parametrize(
    "breaks",
    [
        "Breaks: Acceptance line 2",
        "Breaks: repro `pytest tests/test_pay.py`",
        f"{STANDING}\n{PATH}",
    ],
)
def test_a_major_that_breaks_an_acceptance_line_a_repro_or_a_standing_bar_with_a_path_is_accepted(
    tmp_path: Path, breaks: str
) -> None:
    got = facts(tmp_path, report(finding("major", breaks), one("major"), "no"))
    assert got["verdict"]["major"] == 1 and got["satisfied"] is False


def test_a_security_finding_with_a_path_and_no_acceptance_link_is_a_major_and_without_a_path_a_minor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert facts(tmp_path, report(finding("major", STANDING, PATH), one("major"), "no"))["findings"]
    out = refused(tmp_path, report(finding("major", STANDING), one("major"), "no"), capsys)
    assert "no `Path:" in out and "it is a minor" in out
    assert facts(tmp_path, report(finding("minor", STANDING), one("minor"), "yes"))["satisfied"]


@pytest.mark.parametrize("line", ["", "Breaks: a surviving mutant", "Breaks: it is wrong"])
def test_a_major_or_blocker_with_no_readable_breaks_field_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], line: str
) -> None:
    out = refused(tmp_path, report(finding("major", line), one("major"), "no"), capsys)
    assert "F1 is a major with no `Breaks:" in out


def test_replaying_the_surviving_mutant_and_test_strength_passes_of_3008_yields_no_major(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Passes 6 to 8 of #3008 asked for stronger tests of the last round's tests and listed surviving mutants: as
    majors the parser refuses them, as minors they leave the pass satisfied."""
    asks = [
        ("F1", "a surviving mutant in the gate-evidence reader", "Breaks: a surviving mutant"),
        ("F2", "the new test asserts only the exit code", "Breaks: test strength"),
        ("F3", "the fix round's test passes with the guard removed", "Breaks: a surviving mutant"),
    ]
    text = lambda kind: "\n".join(
        f"### {n} ({kind}) {AT}: {title}\n\n{why}\n" for n, title, why in asks
    )
    as_majors = report(text("major"), "0 blocker, 3 major, 0 minor", "no")
    assert "F1 is a major with no" in refused(tmp_path, as_majors, capsys)
    got = facts(tmp_path, report(text("minor"), "0 blocker, 0 major, 3 minor", "no"))
    assert got["verdict"]["major"] == 0 and got["satisfied"] is True


@pytest.mark.parametrize(
    "origin",
    ["prior F2 not fixed", "regression of 1a2b3c4", "present at 9f8e7d6", "new"],
)
def test_each_origin_of_a_delta_finding_reads(tmp_path: Path, origin: str) -> None:
    got = facts(
        tmp_path,
        report(
            finding("major", "Breaks: Acceptance line 1", f"Origin: {origin}"),
            one("major"),
            "no",
            2,
        ),
    )
    assert got["findings"][0]["severity"] == "major"


def test_a_delta_major_with_no_or_an_unreadable_origin_is_refused_and_a_first_pass_needs_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = report(finding("major", "Breaks: Acceptance line 1"), one("major"), "no", 2)
    assert "no `Origin:` line" in refused(tmp_path, broken, capsys)
    odd = report(
        finding("major", "Breaks: Acceptance line 1", "Origin: somewhere"), one("major"), "no", 2
    )
    assert "can't read `Origin: somewhere`" in refused(tmp_path, odd, capsys)
    assert facts(
        tmp_path, report(finding("major", "Breaks: Acceptance line 1"), one("major"), "no")
    )


def test_a_major_marked_present_at_an_earlier_head_is_rejected_unless_it_breaks_an_acceptance_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = "Origin: present at 9f8e7d6"
    out = refused(
        tmp_path, report(finding("major", STANDING, PATH, old), one("major"), "no", 2), capsys
    )
    assert "breaks no Acceptance line" in out
    assert facts(tmp_path, report(finding("minor", STANDING, old), one("minor"), "yes", 2))[
        "satisfied"
    ]
    kept = report(finding("major", "Breaks: Acceptance line 1", old), one("major"), "no", 2)
    assert facts(tmp_path, kept)["verdict"]["major"] == 1


@pytest.mark.parametrize(
    ("verdict", "findings", "extra", "wrote", "satisfied"),
    [
        ("0 blocker, 0 major, 1 minor", finding("minor"), "", "no", True),
        ("0 blocker, 0 major, 0 minor", "", "", "no", True),
        ("0 blocker, 0 major, 1 minor", finding("minor"), "Not run: the e2e gate\n", "no", False),
        (
            "0 blocker, 1 major, 0 minor",
            finding("major", "Breaks: Acceptance line 1"),
            "",
            "yes",
            False,
        ),
    ],
)
def test_the_counts_decide_satisfaction_whatever_the_satisfied_line_says(
    tmp_path: Path, verdict: str, findings: str, extra: str, wrote: str, satisfied: bool
) -> None:
    got = facts(tmp_path, report(findings, verdict, wrote, extra=extra))
    assert got["satisfied"] is satisfied


@pytest.mark.parametrize(
    "path_line", ["path: POST /pay with a forged token skips the auth check.", "  PATH: POST /pay"]
)
def test_a_path_line_reads_in_any_case_and_indented(tmp_path: Path, path_line: str) -> None:
    got = facts(tmp_path, report(finding("major", STANDING, path_line), one("major"), "no"))
    assert got["findings"][0]["severity"] == "major"


@pytest.mark.parametrize(
    "lines",
    [
        ("File Path: auth.py",),
        ("```", "Path: POST /pay", "```"),
    ],
)
def test_a_path_that_is_not_a_line_of_its_own_does_not_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], lines: tuple[str, ...]
) -> None:
    out = refused(tmp_path, report(finding("major", STANDING, *lines), one("major"), "no"), capsys)
    assert "no `Path: <input, steps, impact>` line" in out


@pytest.mark.parametrize(
    "origin",
    ["Origin:  present at 9f8e7d6", "Origin:present at 9f8e7d6", "Origin:\tpresent at 9f8e7d6"],
)
def test_any_spacing_after_origin_is_refused_as_present_at(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], origin: str
) -> None:
    text = report(finding("major", STANDING, PATH, origin), one("major"), "no", 2)
    assert "breaks no Acceptance line" in refused(tmp_path, text, capsys)
