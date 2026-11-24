"""approvals.py: a level's `rerun` (#2240). A high-risk head merges only on an independent rerun of its selection: a
record of `local-ci --record --rerun` on its tree that an app pushed (a CI run) or that a verifier pass on the head
names on a `Rerun:` line (a fresh session the verifier started). The worker's own record, or a rerun record a person's
account pushed by hand, is no such proof; a low-risk head still merges on the worker's record (#2143's D1)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (  # noqa: F401
    HEAD,
    TREE,
    approvals,
    gating,
    git_in,
    judged_pr,
    judging,
    loop_md,
    pull,
)
from test_approvals_narrowed_gate import repo  # noqa: F401

Gate = tuple[dict[str, Any], list[tuple[int, str]]]

# the real check and the real record push, which the harness's `reran` and `refs` fixtures replace for other modules
REAL_GAP, REAL_PUSH = approvals.rerun_gap, approvals.push_record
RERUN_REF = f"refs/heads/loop-gate/{TREE}-111111111111"
RERUN_COMMIT = "c" * 40
GATES = "risk:\n  verifier: true\nlevels:\n  high:\n    merge: gates\n"
ASKED = "PR #7 is rated high, and `levels.high.rerun` asks an independent rerun of its selection on its head:"


@pytest.fixture
def forge(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The real rerun check, on origin's rerun records (`records`, as reruns() lists them) and the forge's newest push
    to each branch (`pushes`, by ref), the head's tree TREE."""
    state: dict[str, Any] = {"records": [], "pushes": {}}
    monkeypatch.setattr(approvals, "rerun_gap", REAL_GAP)
    monkeypatch.setattr(approvals, "tree_of", lambda _commit: TREE)
    monkeypatch.setattr(approvals, "reruns", lambda held: state["records"] if held == TREE else [])
    monkeypatch.setattr(approvals, "pusher", lambda ref: state["pushes"].get(ref))
    return state


def policy(settings: str) -> None:
    Path("docs/agents/loop.md").write_text(loop_md(settings))


def check_merge(capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    code = approvals.main(["check", "merge", "7"])
    return code, capsys.readouterr().out.splitlines()


def naming(commit: str) -> dict[str, Any]:
    """A satisfied low-risk verifier review on the head whose report names a rerun record's commit."""
    review = judging("low — fine")
    return {**review, "body": review["body"] + f"Rerun: {commit}\n"}


def test_a_high_risk_head_with_only_the_workers_record_is_refused(
    gating: Gate, forge: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """The worker's record carries no rerun mark, so reruns() lists none, and the merge is refused."""
    state, _ = gating
    policy(GATES)
    state["pull"] = judged_pr(judging("low — fine"), labels=("risk:high",))
    code, out = check_merge(capsys)
    assert code == 1
    assert out == [
        (
            f"{ASKED} origin holds no rerun record on tree {TREE}. Where the repo has CI, a CI run on the head runs"
            " `local-ci --record --rerun` and pushes its record; with no CI, the verifier starts a fresh session that"
            " runs it on the head and names the record's commit on a `Rerun: <commit>` line of its report"
        )
    ]


def test_a_rerun_record_a_person_pushed_by_hand_is_refused(
    gating: Gate, forge: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    state, _ = gating
    policy(GATES)
    forge["records"] = [(RERUN_REF, RERUN_COMMIT)]
    forge["pushes"][RERUN_REF] = {"after": RERUN_COMMIT, "login": "worker", "app": False}
    state["pull"] = judged_pr(judging("low — fine"), labels=("risk:high",))
    code, out = check_merge(capsys)
    assert code == 1
    assert out[0].startswith(
        f"{ASKED} origin holds 1 rerun record(s) on tree {TREE}, but none an app pushed or a verifier pass on the"
        " head names."
    )


def test_a_rerun_record_an_app_pushed_lets_a_high_risk_head_merge(
    gating: Gate, forge: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    state, _ = gating
    policy(GATES)
    forge["records"] = [(RERUN_REF, RERUN_COMMIT)]
    forge["pushes"][RERUN_REF] = {"after": RERUN_COMMIT, "login": "github-actions", "app": True}
    state["pull"] = judged_pr(judging("low — fine"), labels=("risk:high",))
    assert check_merge(capsys) == (0, [])
    # an app's push that set the branch to another commit than its tip is someone else's tip
    forge["pushes"][RERUN_REF] = {"after": "d" * 40, "login": "github-actions", "app": True}
    assert check_merge(capsys)[0] == 1


def test_a_rerun_record_the_verifier_names_lets_a_high_risk_head_merge(
    gating: Gate, forge: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """With no CI, the verifier's fresh session pushes under the shared account; the verdict naming it is the fact."""
    state, _ = gating
    policy(GATES)
    forge["records"] = [(RERUN_REF, RERUN_COMMIT)]
    forge["pushes"][RERUN_REF] = {"after": RERUN_COMMIT, "login": "worker", "app": False}
    state["pull"] = judged_pr(naming(RERUN_COMMIT), labels=("risk:high",))
    assert check_merge(capsys) == (0, [])
    # a name that is no rerun record's commit names nothing
    state["pull"] = judged_pr(naming("d" * 40), labels=("risk:high",))
    assert check_merge(capsys)[0] == 1
    # nor does a pass on another head
    state["pull"] = judged_pr(
        {**naming(RERUN_COMMIT), "commit": {"oid": "f" * 40}}, labels=("risk:high",)
    )
    assert any(ASKED in line for line in check_merge(capsys)[1])


def test_a_low_risk_head_merges_on_the_workers_record(
    gating: Gate, forge: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """No rerun record at all: the default `levels.low.rerun: false` keeps the worker's record as the proof."""
    state, _ = gating
    policy("risk:\n  verifier: true\n")
    state["pull"] = judged_pr(judging("low — fine"))
    assert check_merge(capsys) == (0, [])


def test_each_level_takes_its_own_rerun_option(
    gating: Gate, forge: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    state, _ = gating
    policy(GATES + "    rerun: false\n")
    state["pull"] = judged_pr(judging("low — fine"), labels=("risk:high",))
    assert check_merge(capsys) == (0, [])
    policy("risk:\n  verifier: true\nlevels:\n  low:\n    rerun: true\n")
    state["pull"] = judged_pr(judging("low — fine"))
    code, out = check_merge(capsys)
    assert code == 1
    assert out[0].startswith(
        "PR #7 is rated low, and `levels.low.rerun` asks an independent rerun of its selection on its head:"
    )


def test_rerun_is_a_boolean_per_level() -> None:
    with pytest.raises(approvals.Refused) as refused:
        approvals.settings(loop_md("levels:\n  high:\n    rerun: sometimes\n"))
    assert "levels" in str(refused.value) and "rerun" in str(refused.value)


# --- the rerun's record: local-ci --record --rerun, and reruns() on a real origin ---


def test_a_rerun_runs_again_whatever_is_recorded_and_records_apart(
    repo: dict[str, Any],
    refs: dict[str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In a repo with CI, the worker's narrowed record exists; the rerun still runs the selection, narrowed against
    the merge base, and records under a command naming LOOP_RERUN, so its key is not the worker's."""
    monkeypatch.delenv(approvals.RERUN_VAR, raising=False)
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    base = git_in(repo["work"], "merge-base", "origin/main", "HEAD").strip()
    assert approvals.main(["local-ci", "--record", "--base", base]) == 0
    assert (
        approvals.main(["local-ci", "--record", "--base", base]) == 0
    )  # the worker's pass, reused
    assert len(repo["ran"]()) == 1
    assert approvals.main(["local-ci", "--record", "--rerun"]) == 0
    assert repo["ran"]() == [f"selected app.py docs/agents/loop.md against {base}"] * 2
    commands = sorted(record["command"] for record in refs.values())
    assert len(commands) == 2
    rerun = next(record for record in refs.values() if approvals.RERUN_VAR in record["env"])
    assert rerun["command"].startswith(f"GATE_BASE={base} {approvals.RERUN_VAR}=1 ")
    assert approvals.narrowed_base(rerun["command"]) == base
    # a second rerun runs again too: nothing it finds is reused
    assert approvals.main(["local-ci", "--record", "--rerun"]) == 0
    assert len(repo["ran"]()) == 3


def test_a_rerun_whose_record_cannot_reach_origin_fails(
    repo: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A branch of the rerun's name already on origin (someone else's) refuses the push: the rerun exits 1, since a
    record only this clone holds is none rerun_gap reads, where a worker's pass would only say so."""

    def refused(_record: dict[str, Any]) -> str:
        raise subprocess.CalledProcessError(1, "git push", stderr="rejected: non-fast-forward")

    monkeypatch.delenv(approvals.RERUN_VAR, raising=False)
    monkeypatch.setattr(approvals, "push_record", refused)
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    assert approvals.main(["local-ci", "--record", "--rerun"]) == 1
    assert (
        "the rerun's record was not pushed to origin, so no gate reads it: rejected"
        in capsys.readouterr().out
    )


@pytest.mark.parametrize(
    "argv",
    [["local-ci", "7", "--rerun"], ["local-ci", "--record", "--head-proof", "--rerun"]],
    ids=["with-a-pr", "with-head-proof"],
)
def test_rerun_goes_with_record_alone(
    argv: list[str], gating: Gate, capsys: pytest.CaptureFixture[str]
) -> None:
    policy("loop:\n  head_proof:\n    status: gate-ui\n    env:\n      - GATE_UI\n")
    assert approvals.main(argv) == 1
    assert "--rerun goes with --record alone" in capsys.readouterr().out


def test_reruns_lists_only_the_rerun_records_on_origin(
    repo: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pushed for real: the worker's record of the same tree and a rerun record; only the rerun's is listed, and
    one whose commit holds another tree than its name says is not."""
    monkeypatch.setattr(approvals, "push_record", REAL_PUSH)
    repo["loop"]("# Loop\n")
    head = repo["head"]()
    held = git_in(repo["work"], "rev-parse", "HEAD^{tree}").strip()
    when = "2026-01-01T00:00:00Z"
    worker = {"head": head, "tree": held, "command": "mise run check", "env": {}, "time": when}
    approvals.push_record(worker)
    rerun = {
        "head": head,
        "tree": held,
        "command": f"{approvals.RERUN_VAR}=1 mise run check",
        "env": {approvals.RERUN_VAR: "1"},
        "time": when,
    }
    ref = approvals.push_record(rerun)
    tip = git_in(repo["work"], "ls-remote", "origin", ref).split()[0]
    assert approvals.reruns(held) == [(ref, tip)]
    # a branch named for this tree whose commit holds another, its message copied from the real record
    other = git_in(repo["work"], "rev-parse", "HEAD~1^{tree}").strip()
    message = git_in(repo["work"], "cat-file", "commit", tip).partition("\n\n")[2]
    forged = git_in(
        repo["work"], "commit-tree", other, "-p", head, "-m", message.rstrip("\n")
    ).strip()
    git_in(
        repo["work"], "push", "-q", "origin", f"{forged}:refs/heads/loop-gate/{held}-222222222222"
    )
    assert approvals.reruns(held) == [(ref, tip)]
    assert approvals.reruns("0" * 40) == []


def test_pusher_reads_the_newest_push_and_whether_an_app_made_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    def rest(path: str) -> Any:
        asked.append(path)
        return [{"after": RERUN_COMMIT, "actor": {"login": "github-actions[bot]", "type": "Bot"}}]

    monkeypatch.setattr(approvals.github, "rest", rest)
    assert approvals.github.pusher(RERUN_REF) == {
        "after": RERUN_COMMIT,
        "login": "github-actions[bot]",
        "app": True,
    }
    assert asked == [
        f"repos/{{owner}}/{{repo}}/activity?ref=refs%2Fheads%2Floop-gate%2F{TREE}-111111111111&per_page=1"
    ]
    # a person's account, as a cloud worker's push shows, is no app
    monkeypatch.setattr(
        approvals.github,
        "rest",
        lambda _path: [{"after": RERUN_COMMIT, "actor": {"login": "worker", "type": "User"}}],
    )
    assert approvals.github.pusher(RERUN_REF)["app"] is False
    monkeypatch.setattr(approvals.github, "rest", lambda _path: [])
    assert approvals.github.pusher(RERUN_REF) is None


# --- the verifier's brief in a repo with no CI ---


def brief(
    settings: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> list[str]:
    """`brief 7`'s `- Rerun:` lines under a loop.md with `settings`."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pull(body="Closes #12.\n"))
    monkeypatch.setattr(approvals, "merge_base", lambda base, head: "b" * 40)
    monkeypatch.setattr(approvals, "project", lambda: (None, loop_md(settings)))
    assert approvals.main(["brief", "7"]) == 0
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith("- Rerun:")]


def test_with_no_ci_the_verifiers_brief_says_to_start_the_rerun_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    [line] = brief("loop:\n  ci: false\n", monkeypatch, tmp_path, capsys)
    assert line.startswith(
        "- Rerun: this repo has no CI, and gatekeeper.md's `levels` asks an independent rerun for a high or critical"
        " head; where the head rates so (your own `Risk: high` makes it high), start a fresh cloud session that runs `uv run "
    )
    assert line.endswith(
        f"approvals.py local-ci --record --rerun` on a clean checkout of {HEAD} and returns the commit of the record"
        " branch it pushed, then write `Rerun: <that commit>` in your report, since `check merge` refuses that head"
        " without it"
    )


def test_with_ci_or_no_level_asking_a_rerun_the_brief_says_nothing_of_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert brief("", monkeypatch, tmp_path, capsys) == []
    off = "loop:\n  ci: false\nlevels:\n  high:\n    rerun: false\n  critical:\n    rerun: false\n"
    assert brief(off, monkeypatch, tmp_path, capsys) == []
