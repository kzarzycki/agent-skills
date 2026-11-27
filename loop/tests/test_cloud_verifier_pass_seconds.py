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
    """`checkout` with `gh`'s comment calls replaced: a post answers what its `--jq` selects from the created comment,
    as `gh` does, and an edit is recorded."""
    _, _, brief, _, seen = checkout
    seen["report"] = REPORT
    inner = cv.run
    posts: list[str] = []
    edits: list[tuple[str, str]] = []

    def run(*cmd: str, check: bool = True, **kw):
        if (
            cmd[:2] == ("gh", "api")
            and "--paginate" not in cmd
            and any("/issues/" in word for word in cmd)
        ):
            if "PATCH" in cmd:
                if seen.get("edit fails"):
                    raise cv.Refused("`gh api` exited 1: HTTP 502")
                edits.append((cmd[-3], kw["input"]))
                return cv.subprocess.CompletedProcess(cmd, 0, "", "")
            if seen.get("post fails"):
                raise cv.Refused("`gh api` exited 1: HTTP 502")
            posts.append(kw["input"])
            made = {"html_url": "https://example.com/comment/1", "id": 42}
            jq = cmd[cmd.index("--jq") + 1] if "--jq" in cmd else ""
            out = "".join(f"{made[f.strip().lstrip('.')]}\n" for f in jq.split(",") if f.strip())
            return cv.subprocess.CompletedProcess(cmd, 0, out, "")
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
    assert (
        body.rstrip("\n").splitlines()[-6:-2] == lines and len(lines) == 4
    )  # the folded timing block's four lines
    assert body.rstrip("\n").splitlines()[-2:] == ["", "</details>"]
    return dict(line[len("Seconds: ") :].split(" ", 1) for line in lines)


def test_a_pass_with_requested_posts_four_numbers_and_edits_the_post_time_once(pass_run) -> None:
    brief, _, posts, edits = pass_run
    assert cv.verify(7, brief, None, None, requested=time.time() - 5) == 0
    assert len(posts) == 1 and len(edits) == 1
    assert footer(posts[0])["post"] == "unknown"  # known only after the post
    assert posts[0].startswith(
        cv.folded_report(REPORT).rstrip("\n")
    )  # the folded report, then the timing fold
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

    scripts = (
        Path(cv.__file__).resolve().parents[4] / "gatekeeper" / "skills" / "gatekeeper" / "scripts"
    )
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


def test_a_requested_later_than_the_pass_start_is_unknown_never_zero(pass_run) -> None:
    brief, _, _, edits = pass_run
    # the lead's clock runs 90 s ahead of the VM's, so the span runs backwards
    assert cv.verify(7, brief, None, None, requested=time.time() + 90) == 0
    assert footer(edits[0][1])["start"] == "unknown"
    assert cv.seconds(100.0, 10.0, 12.0, 20.0)["start"] is None


def test_requested_reaches_the_pass_from_the_command_line(pass_run) -> None:
    brief, _, _, edits = pass_run
    argv = ["verify", "--pr", "7", "--brief", str(brief), "--requested", str(time.time() - 4)]
    assert cv.command(argv) == 0
    assert int(footer(edits[0][1])["start"]) >= 4


@pytest.mark.parametrize("why", ["no report", "repeated question", "refused post"])
def test_a_pass_that_ran_but_posted_nothing_still_prints_its_json_line(
    pass_run, capsys, why
) -> None:
    brief, seen, posts, _ = pass_run
    if why == "no report":
        seen.update(report="no verdict here\n", final="nothing\n")
    elif why == "repeated question":
        brief.write_text(f"{brief.read_text()}\n## Answer to your question\n\nRun it.\n")
        seen["question"] = "Please run the gate again.\n"
    else:
        seen["post fails"] = True
    assert cv.verify(7, brief, None, None, requested=time.time() - 2) == 1
    assert not posts
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["pass_seconds"]["start"] >= 2 and line["pass_seconds"]["review"] >= 1
    assert line["pass_seconds"]["post"] is None
