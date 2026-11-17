"""approvals.py: `land --wait` follows the base when another land moves its code while it waits (#1280)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    git_in,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    lands,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

REAL = approvals.judge_with_base  # the shared fixtures replace it per test
LANDING = approvals.landing  # the fixture below replaces it
SCRIPT = "scripts/approvals.py"


class Restarted(Exception):
    """os.execv, which the test can't let replace pytest."""


@pytest.fixture
def waiting(monkeypatch: pytest.MonkeyPatch, lands: dict[str, Any], pushed: None) -> dict[str, Any]:
    """A checkout of the base's branch running a copy of the script that is on origin's main, whose landing() takes
    the lock and judges with the base as the real one does; os.execv recorded, not taken."""
    monkeypatch.setattr(approvals, "judge_with_base", REAL)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv(approvals.DEADLINE_ENV, raising=False)
    work = lands["work"]
    script = work / SCRIPT
    script.parent.mkdir()
    script.write_text(Path(approvals.__file__).read_text())
    (work / "SKILL.md").write_text(
        (Path(approvals.__file__).parent.parent / "SKILL.md").read_text()
    )
    monkeypatch.setattr(approvals, "__file__", str(script))
    monkeypatch.setattr(approvals, "RUNNING", (str(script),))
    git_in(work, "add", "-A")
    git_in(work, "commit", "-qm", "adopt the loop")
    git_in(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git_in(work, "fetch", "-q", "origin")
    git_in(work, "checkout", "-q", "-B", "main", "origin/main")
    execs: list[tuple[str, list[str], str | None]] = []

    def execv(path: str, argv: list[str]) -> None:
        execs.append((path, argv, approvals.os.environ.get(approvals.DEADLINE_ENV)))
        raise Restarted

    monkeypatch.setattr(approvals.os, "execv", execv)

    def landing(_pr: Any, _only: bool = False) -> tuple[int, bool]:
        approvals.judge_with_base("main", fetch=True)
        return 0, False

    monkeypatch.setattr(approvals, "landing", landing)
    return lands | {"execs": execs}


def moved(state: dict[str, Any], tmp: Path) -> str:
    """Another land merges a change to the script into origin's main: the new tip."""
    other = tmp / "other"
    git_in(tmp, "clone", "-q", str(state["origin"]), str(other))
    (other / SCRIPT).write_text((other / SCRIPT).read_text() + "\n# another land's change\n")
    git_in(
        other,
        "-c",
        "user.email=l@example.com",
        "-c",
        "user.name=l",
        "commit",
        "-qam",
        "move the base",
    )
    git_in(other, "push", "-q", "origin", "HEAD:refs/heads/main")
    return git_in(other, "rev-parse", "HEAD").strip()


def test_a_waiting_land_whose_base_moved_its_script_follows_the_base_and_lands(
    waiting: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work, tip = waiting["work"], moved(waiting, tmp_path)
    with pytest.raises(Restarted):
        approvals.land(7, wait=True)
    assert git_in(work, "rev-parse", "HEAD").strip() == tip  # no manual pull
    assert (work / SCRIPT).read_text().endswith("# another land's change\n")
    [(path, argv, deadline)] = waiting["execs"]
    assert (path, argv) == (sys.executable, [sys.executable, *sys.argv])
    assert deadline and float(deadline) <= time.monotonic() + approvals.CEILING
    out = capsys.readouterr().out
    assert "differs from origin/main's" in out and "fast-forwarded to origin/main" in out
    # the run in place of this one: the new code judges and lands, inside the first run's ceiling
    assert approvals.land(7, wait=True) == 0
    assert approvals.DEADLINE_ENV not in approvals.os.environ


@pytest.mark.parametrize(
    "checkout",
    ["an edited tracked file", "a detached head", "another branch", "a commit the base lacks"],
)
def test_any_other_checkout_keeps_the_refusal(
    waiting: dict[str, Any], tmp_path: Path, checkout: str
) -> None:
    work = waiting["work"]
    if checkout == "an edited tracked file":
        (work / "app.py").write_text("value = 2\n")
    elif checkout == "a commit the base lacks":  # no fast-forward
        git_in(work, "commit", "-q", "--allow-empty", "-m", "local")
    else:
        git_in(
            work, "switch", "-q", *(["--detach"] if checkout == "a detached head" else ["-c", "pr"])
        )
    before = git_in(work, "rev-parse", "HEAD").strip()
    moved(waiting, tmp_path)
    with pytest.raises(approvals.Drifted, match="a PR's own copy would judge it"):
        approvals.land(7, wait=True)
    assert git_in(work, "rev-parse", "HEAD").strip() == before
    assert waiting["execs"] == []


def test_a_drift_the_fast_forward_leaves_keeps_the_refusal(waiting: dict[str, Any]) -> None:
    """The running script in the checkout but untracked at the base: drift no fast-forward clears, so no run again."""
    work = waiting["work"]
    git_in(work, "rm", "-q", "--cached", SCRIPT)
    git_in(work, "commit", "-qm", "untrack the script")
    git_in(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    with pytest.raises(approvals.Drifted):
        approvals.land(7, wait=True)
    assert waiting["execs"] == []


def test_the_lock_is_released_before_the_run_again(
    waiting: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real landing: the base moves while the lock is held, so the drift is found under it."""
    monkeypatch.setattr(approvals, "landing", LANDING)
    work = waiting["work"]
    waiting["open"](7, {"feature.txt": "x\n"})
    git_in(work, "checkout", "-q", "main")
    take, held = approvals.locked, []

    def locked(*args: Any, **kwargs: Any) -> bool:
        taken = take(*args, **kwargs)
        held.append(waiting["lock"]())
        moved(waiting, tmp_path)
        return taken

    monkeypatch.setattr(approvals, "locked", locked)
    with pytest.raises(Restarted):
        approvals.land(7, wait=True)
    assert len(waiting["execs"]) == 1
    assert held and held[0]  # the drift was found under the lock
    assert waiting["lock"]() == ""  # and the lock was released before the run again


def test_without_wait_the_refusal_stands(waiting: dict[str, Any], tmp_path: Path) -> None:
    before = git_in(waiting["work"], "rev-parse", "HEAD").strip()
    moved(waiting, tmp_path)
    with pytest.raises(approvals.Drifted):
        approvals.land(7)
    assert git_in(waiting["work"], "rev-parse", "HEAD").strip() == before
    assert waiting["execs"] == []


def test_the_run_again_keeps_the_first_runs_ceiling(
    waiting: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "landing", lambda _pr, _only=False: (approvals.WAITING, True))
    monkeypatch.setenv(approvals.DEADLINE_ENV, repr(time.monotonic() - 1))
    monkeypatch.setattr(
        approvals.time, "sleep", lambda _s: pytest.fail("waited past the first run's ceiling")
    )
    assert approvals.land(7, wait=True) == approvals.WAITING  # at once: no fresh 2 hours
