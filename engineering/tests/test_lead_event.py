"""The lead event (#1376): ``wait-on`` and ``end-on`` print the ending line and write the ``lead`` event, and the
supervisor reads the event before the prose."""

import subprocess
from pathlib import Path

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

oa = base.omnigent_agent
BRANCH = "loop/x"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A checkout on ``loop/x`` of a temporary bare ``origin``, as the current directory."""
    bare, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True, capture_output=True)
    git(work, "checkout", "-q", "-b", BRANCH)
    git(
        work,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    monkeypatch.chdir(work)
    return work


def run(*argv: str, capsys: pytest.CaptureFixture[str]) -> str:
    assert oa.main(list(argv)) == 0
    return capsys.readouterr().out.strip()


class Workspace(base.Lead):
    """The followed lead ``a``, whose workspace is ``path``."""

    def __init__(self, path: Path, *items: dict) -> None:
        super().__init__(*items)
        self.snap = {"workspace": str(path)}


def test_needs_owner_carries_the_whole_question(
    clone: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    question = tmp_path / "q.md"
    text = "Should the epic split?\n" + "\n".join(f"- option {n}: " + "x" * 90 for n in range(20))
    text = text[:2000]
    question.write_text(text)
    line = run("end-on", "needs-owner", "--question", str(question), capsys=capsys)
    assert oa.ending_of(line) == "USER NEEDED" and "\n" not in line
    ref = f"refs/loop/lead/{BRANCH}"
    assert git(clone, "show", f"{ref}:question.md") == text.strip()  # whole, and on origin too
    assert git(clone, "ls-remote", "origin", ref)
    og = Workspace(clone, base.told("brief", 60), base.ending(line, 1))
    base.supervised(og, base.following(tmp_path), monkeypatch, 3, notify="cos", console=True)
    [post] = base.posted(og)
    assert "[owner]" in post and text.strip() in post  # all 2,000 characters reach the owner


def test_event_beats_cos_footer(clone: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = "STILL WORKING: spec filed\nCoS: please approve #12"
    lead = {"named": []}
    assert oa.waits_on(text, lead, "cos")  # without an event the footer decides, as before
    run("wait-on", "ci", capsys=capsys)
    event = oa.lead_event_of(base.Fleet(), {"workspace": str(clone)})
    assert event and event["state"] == "waiting"
    assert not oa.waits_on(text, lead, "cos", bool(event))
    # a Waits: line that parses still decides
    assert oa.waits_on("STILL WORKING: x\nWaits: supervisor", lead, "cos", True)


def test_unparsed_wait_notice_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = base.following(tmp_path)
    offset = base.skewed(monkeypatch)
    og = base.Lead(base.told("brief", 800), base.ending("STILL WORKING: x\nWaits: soonish", 600))

    def later(poll: int) -> None:
        offset[0] = 100.0 * poll * 4

    base.supervised(og, registry, monkeypatch, 5, later, notify="cos", console=True)
    notices = [
        t for s, t in og.inbox if s == "a" and "did not parse" in t
    ]  # a nudge is another message
    assert len(notices) == 1
    assert "Accepted:" in notices[0]  # the accepted forms


def test_end_line_round_trips(
    clone: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for words, wait in [(["supervisor"], "supervisor"), (["pr", "7"], "#7"), (["ci"], "CI")]:
        line = run("wait-on", *words, capsys=capsys)
        assert line == oa.wait_line(words)  # the line wait-on printed before this change
        assert oa.wait_of(f"STILL WORKING: x\n{line}") == wait
    done = run("end-on", "done", "PR 7 merged", "--report", "r.md", capsys=capsys)
    assert done == "DONE: PR 7 merged. Report: r.md" and oa.ending_of(done) == "DONE"
    assert oa.ending_of(
        run("end-on", "needs-owner", "--question", str(_q(tmp_path)), capsys=capsys)
    ) == ("USER NEEDED")


def _q(tmp_path: Path) -> Path:
    path = tmp_path / "q2.md"
    path.write_text("Approve the split?\nbecause of x")
    return path


def test_an_emit_that_cannot_write_never_changes_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)  # not a checkout: no branch, no event
    assert run("wait-on", "ci", capsys=capsys) == "Waits: CI"
    monkeypatch.setattr(oa.EVENTS, "emit", lambda *a, **k: 1 / 0)
    assert run("wait-on", "ci", "--branch", "b", capsys=capsys) == "Waits: CI"


def quiet_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, og: base.Lead) -> str:
    """Supervise ``og``'s lead ``a`` past a quiet turn end; the log of how each event was settled."""
    registry = base.following(tmp_path)
    offset = base.skewed(monkeypatch)
    base.supervised(
        og, registry, monkeypatch, 3, lambda poll: offset.__setitem__(0, 400.0 * poll),
        notify="cos", console=True,
    )  # fmt: skip
    return registry.with_suffix(".events.jsonl").read_text()


def test_a_lead_with_an_event_is_not_told_its_wait_did_not_parse(
    clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run("wait-on", "ci", capsys=capsys)
    og = Workspace(
        clone, base.told("brief", 800), base.ending("STILL WORKING: x\nWaits: soonish", 600)
    )
    quiet_end(tmp_path, monkeypatch, og)
    assert not [t for s, t in og.inbox if s == "a" and "did not parse" in t]


def test_a_cos_footer_is_a_wait_on_the_supervisor_only_without_an_event(
    clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    last = "STILL WORKING: spec filed\nCoS: please approve #12"
    plain = quiet_end(_d(tmp_path, "p"), monkeypatch, base.Lead(base.ending(last, 600)))  # type: ignore[arg-type]
    assert "waits on its supervisor" in plain
    run("wait-on", "ci", capsys=capsys)
    with_event = quiet_end(_d(tmp_path, "e"), monkeypatch, Workspace(clone, base.ending(last, 600)))  # type: ignore[arg-type]
    assert "waits on its supervisor" not in with_event


def _d(root: Path, name: str) -> Path:
    (root / name).mkdir()
    return root / name
