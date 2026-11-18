"""scripts/cloud_verifier.py verify: each pass's start, setup, review and post seconds, as a `Seconds:` footer on the
posted comment and one JSON line on stdout. `gh` and the CLIs are stand-ins; the timing and footer code runs."""

from __future__ import annotations

import json
import time

import pytest
from test_cloud_verifier import checkout, cv, git  # noqa: F401 - `checkout` is a fixture
from test_cloud_verifier_claude import claude  # noqa: F401 - a fixture

REPORT = "# Report\n\nHead: x\nVERDICT: 0 blocker\nSATISFIED: yes\nRisk: low\n"


@pytest.fixture
def pass_run(checkout, monkeypatch):  # noqa: F811 - the imported fixture, used by name
    """`checkout` with `gh`'s comment calls replaced: a post answers a URL and an id, an edit is recorded."""
    _, _, brief, _, seen = checkout
    seen["report"] = REPORT
    inner = cv.run
    posts: list[str] = []
    edits: list[tuple[str, str]] = []

    def run(*cmd: str, check: bool = True, **kw):
        if cmd[:2] == ("gh", "api") and any("/issues/" in word for word in cmd):
            if "PATCH" in cmd:
                if seen.get("edit fails"):
                    raise cv.Refused("`gh api` exited 1: HTTP 502")
                edits.append((cmd[-3], kw["input"]))
            else:
                posts.append(kw["input"])
            return cv.subprocess.CompletedProcess(cmd, 0, "https://example.com/comment/1\n42\n", "")
        return inner(*cmd, check=check, **kw)

    monkeypatch.setattr(cv, "run", run)
    real_codex = cv.codex_exec

    def slow_codex(cmd, text):  # the review takes measurable time
        time.sleep(1.1)
        return real_codex(cmd, text)

    monkeypatch.setattr(cv, "codex_exec", slow_codex)
    return brief, seen, posts, edits


def footer(body: str) -> dict[str, str]:
    lines = [line for line in body.splitlines() if line.startswith("Seconds: ")]
    assert body.rstrip("\n").splitlines()[-4:] == lines and len(lines) == 4  # the last four lines
    return dict(line[len("Seconds: ") :].split(" ", 1) for line in lines)


def test_a_pass_with_requested_posts_four_numbers_and_edits_the_post_time_once(pass_run) -> None:
    brief, _, posts, edits = pass_run
    assert cv.verify(7, brief, None, None, requested=time.time() - 5) == 0
    assert len(posts) == 1 and len(edits) == 1
    assert footer(posts[0])["post"] == "unknown"  # known only after the post
    assert posts[0].startswith(REPORT)  # the report, unchanged, then the footer
    got = footer(edits[0][1])
    assert edits[0][0].endswith("/issues/comments/42")
    assert all(got[name].isdigit() for name in cv.PHASES)
    assert int(got["start"]) >= 5 and int(got["review"]) >= 1


def test_a_pass_without_requested_says_start_unknown_and_a_failed_edit_only_warns(
    pass_run, capsys
) -> None:
    brief, seen, posts, edits = pass_run
    seen["edit fails"] = True
    assert cv.verify(7, brief, None, None) == 0
    got = footer(posts[0])
    assert got["start"] == "unknown" and got["post"] == "unknown" and not edits
    out = capsys.readouterr()
    assert "post time was not added" in out.err
    assert json.loads(out.out.splitlines()[-2])["pass_seconds"]["post"] is None


def test_the_json_line_matches_the_footer_and_the_url_stays_last(pass_run, capsys) -> None:
    brief, _, _, edits = pass_run
    assert cv.verify(7, brief, None, None, requested=time.time() - 3) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1] == "https://example.com/comment/1"
    line = json.loads(lines[-2])
    assert line["pr"] == 7 and len(line["head"]) == 40
    assert {k: str(v) for k, v in line["pass_seconds"].items()} == footer(edits[0][1])


def test_a_question_has_no_phase_printed_as_zero(pass_run, capsys) -> None:
    brief, seen, _, edits = pass_run
    seen["question"] = "Please run the gate.\n"
    assert cv.verify(7, brief, None, None) == 3
    shown = footer(edits[0][1])
    assert shown["start"] == "unknown"  # no --requested
    assert shown["setup"].isdigit() and shown["review"].isdigit()
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-2])
    assert line["pass_seconds"]["start"] is None


def test_a_phase_that_did_not_run_is_unknown_never_zero() -> None:
    assert cv.seconds(None, 10.0, None, None) == {
        "start": None,
        "setup": None,
        "review": None,
        "post": None,
    }
    assert cv.seconds(5.0, 10.0, 12.0, 20.4)["review"] == 8


def test_a_claude_pass_times_its_phases_too(claude, capsys) -> None:  # noqa: F811
    brief, rec = claude[2], claude[5]
    (rec / "do").write_text("report")
    assert cv.verify(7, brief, None, None, "claude", requested=time.time() - 2) == 0
    seconds = json.loads(capsys.readouterr().out.strip().splitlines()[-2])["pass_seconds"]
    assert seconds["start"] >= 2 and seconds["setup"] is not None and seconds["review"] is not None


def test_the_footer_stays_out_of_the_verdict_parsers(tmp_path) -> None:
    import sys
    from pathlib import Path

    scripts = Path(cv.__file__).parent
    sys.path.insert(0, str(scripts))
    try:
        import gatekeeper
    finally:
        sys.path.remove(str(scripts))
    report = tmp_path / "r.md"
    report.write_text(
        "Verifier: codex/x/med, pass 1\n\n## Criteria\n\n- c1\n\n### F1 (minor) a.py:3: a thing\n\nits body\n\n"
        f"Head: {'0' * 40}\nVERDICT: 0 blocker, 0 major, 1 minor\nSATISFIED: yes\nRisk: low — small\n\n"
        "Seconds: start 5\nSeconds: setup 3\nSeconds: review 60\nSeconds: post unknown\n"
    )
    _, _, found, closing, _ = gatekeeper.parse_report(report)
    assert found[0][5] == "its body"  # the last finding's body stops at the closing lines
    assert closing == [
        "VERDICT: 0 blocker, 0 major, 1 minor",
        "SATISFIED: yes",
        "Risk: low — small",
    ]
