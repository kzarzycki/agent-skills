"""scripts/loop.py: the loop's own operations, `brief` and `release`, read through the gatekeeper's ports."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]


def load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


loop = load(
    "loop",
    Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts" / "loop.py",
)
gk = loop.gatekeeper
# the gatekeeper's tests build the PR, issue and review nodes as GitHub returns them
nodes = load("gatekeeper_test_nodes", REPOSITORY / "gatekeeper" / "tests" / "test_approvals.py")
HEAD, BASE, LOOP, PUSHED, LABELED = nodes.HEAD, nodes.BASE, nodes.LOOP, nodes.PUSHED, nodes.LABELED
pull, verdict_on, gatekeeper_md = nodes.pull, nodes.verdict_on, nodes.gatekeeper_md
note, issue, held, assigned_event = nodes.note, nodes.issue, nodes.held, nodes.assigned_event


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No forge preflight, the account running this is `loop` (the gatekeeper's tests write as it), and the
    directory a test runs in is the checkout's root."""
    monkeypatch.setattr(gk, "one_repo", lambda: None)
    monkeypatch.setattr(gk, "viewer", lambda: "loop")
    monkeypatch.setattr(gk, "toplevel", Path.cwd)


@pytest.fixture
def assigned(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Every assignee loop.py adds or removes, instead of making the call."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(gk, "assign", lambda number, login, add: calls.append((number, login, add)))
    return calls


def test_the_gatekeeper_is_found_in_its_sibling_package() -> None:
    assert (
        Path(gk.__file__)
        == REPOSITORY / "gatekeeper" / "skills" / "gatekeeper" / "scripts" / "gatekeeper.py"
    )


def test_a_missing_skill_is_named(tmp_path: Path) -> None:
    """Copied alone, loop.py says which skill to install instead of a traceback."""
    folder = tmp_path / "skills" / "engineering-loop" / "scripts"
    folder.mkdir(parents=True)
    script = folder / "loop.py"
    script.write_text(loop.Path(loop.__file__).read_text())
    import subprocess

    run = subprocess.run(
        [sys.executable, str(script), "release", "1"], capture_output=True, text=True, check=False
    )
    assert run.returncode == 1
    assert (
        run.stderr.strip()
        == "loop.py needs the `gatekeeper` skill: install the package that ships it"
    )


def test_brief_fills_the_facts_from_the_pr_and_refuses_a_stale_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The base is the merge-base with the default branch, the head the PR's, the pass one after the newest verdict
    review's, whose commit is the previous report's head; loop.md's `## Verifier brief` is appended."""
    earlier = "c" * 40
    reviews = (
        verdict_on(earlier, heading="Verifier (codex), pass 1"),
        verdict_on(earlier, heading="Verifier (codex), pass 2"),
    )
    pr = pull(body="Closes #12.\n\n## Evidence\n\nlog\n", reviews=reviews)
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(gk, "pull_request", lambda _n: pr)
    monkeypatch.setattr(gk, "merge_base", lambda base, head: asked.append((base, head)) or BASE)
    monkeypatch.setattr(
        gk,
        "project",
        lambda: (
            None,
            LOOP + "\n## Verifier brief\n\n- Run the full gate bare.\n    indented snippet  \n\n",
        ),
    )
    priorities, proof, stale = tmp_path / "p.md", tmp_path / "gate.log", tmp_path / "old.log"
    priorities.write_text("- the revert path\n")
    proof.write_text(f"{HEAD}\nok\n")
    stale.write_text(f"{earlier}\nok\n")
    assert loop.main(["brief", "7", "--priorities", str(priorities), "--proof", str(proof)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("Review PR #7 as the verifier, pass 3, following ")
    assert out[0].endswith("verifier.md.")
    assert out[1:] == [
        f"- Base: {BASE}",
        f"- Reviewed head: {HEAD}",
        "- Spec: #12",
        "- Report: tmp/loop/pr7-v3.md",
        f"- Previous report: tmp/loop/pr7-v2.md, on {earlier}: review the diff since that head and rerun its repros",
        f"- Proof log: {proof} (its first line is the head)",
        "",
        "Priorities:",
        "- the revert path",
        "",
        "- Run the full gate bare.",
        "    indented snippet  ",
    ]
    assert asked == [("main", HEAD)]
    assert loop.main(["brief", "7", "--proof", str(proof), "--proof", str(stale)]) == 1
    assert (
        capsys.readouterr().out
        == f"PR #7: stale proof, its first line isn't the head {HEAD}: {stale}; rerun it\n"
    )
    # the first line exactly: a trailing space or a CR is not the head; a missing log is named, not a traceback
    for line in (f"{HEAD} ", f"{HEAD}\r"):
        stale.write_bytes(f"{line}\nok\n".encode())
        assert loop.main(["brief", "7", "--proof", str(stale)]) == 1
        assert "stale proof" in capsys.readouterr().out
    assert loop.main(["brief", "7", "--proof", str(tmp_path / "absent.log")]) == 1
    assert capsys.readouterr().out == f"PR #7: no proof log at {tmp_path / 'absent.log'}\n"
    pr["reviews"] = {"nodes": []}
    assert loop.main(["brief", "7"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "- Report: tmp/loop/pr7-v1.md" in out
    assert not [line for line in out if line.startswith("- Previous report")]
    # a policy in gatekeeper.md leaves the Verifier brief in loop.md, the loop's prose
    agents = tmp_path / "docs" / "agents"
    agents.mkdir(parents=True)
    (agents / "loop.md").write_text("## Verifier brief\n\n- Read the loop file's brief.\n")
    monkeypatch.setattr(gk, "toplevel", lambda: tmp_path)
    monkeypatch.setattr(gk, "project", lambda: (None, gk.Policy(gatekeeper_md())))
    assert loop.main(["brief", "7"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "- Read the loop file's brief."


def test_parking_removes_only_the_assignee_the_loop_added(
    monkeypatch: pytest.MonkeyPatch,
    assigned: list[tuple[Any, ...]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    later = "2026-10-01T12:00:00Z"
    by_loop = note("Assigned: @ann\nBy: loop\nPR: #7\n", createdAt=PUSHED)
    found = {
        1: held(issue(1, comments=(by_loop,)), "ann", events=(assigned_event("ann", PUSHED),)),
        2: held(issue(2), "ann", events=(assigned_event("ann", PUSHED),)),  # the owner's own claim
        3: held(
            issue(3, comments=(by_loop,)),
            "ann",
            events=(assigned_event("ann", PUSHED), assigned_event("ann", later)),
        ),  # unassigned, then claimed again by the owner
        4: held(
            issue(4, comments=(by_loop,)), "ann", events=(assigned_event("ann", LABELED),)
        ),  # the loop's assignment, a moment after its record
    }
    monkeypatch.setattr(gk, "issue_node", found.__getitem__)
    for number in found:
        assert loop.main(["release", str(number)]) == 0
    assert assigned == [(1, "ann", False), (4, "ann", False)]
    assert capsys.readouterr().out.splitlines() == [
        "#1: removed @ann, whom the loop assigned",
        "#2: kept @ann, whose claim it is",
        "#3: kept @ann, whose claim it is",
        "#4: removed @ann, whom the loop assigned",
    ]


def test_the_loop_states_the_gatekeepers_default_cap() -> None:
    """The gatekeeper's SKILL.md holds the default; the loop's names the same number, so the two never disagree."""
    skill = (Path(loop.__file__).resolve().parents[1] / "SKILL.md").read_text()
    assert f"The cap is the gatekeeper's: {gk.cap(None)} passes by default" in skill.replace(
        "\n", " "
    )
