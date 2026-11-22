"""omnigent_agent.py: the supervisor runs the gatekeeper's `check stalled` at most hourly for each repo a followed lead
works in, and reports each PR it lists once per head (#1746)."""

from pathlib import Path

import pytest
import test_omnigent_agent as base  # the faked server, the supervisor loop
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent
A, B = "a" * 40, "b" * 40


def line(number: int, head: str, left: str = "is not landed") -> str:
    return f"PR #{number} has its go and a satisfied verdict at {head} and {left}"


class Sweeps:
    """``Sweep`` faked: each run started takes the next of ``outputs`` (exit, text), and ends at once unless
    ``hung``; ``started`` holds each run's workspace, ``stopped`` each one killed."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *outputs: tuple[int, str]) -> None:
        self.outputs, self.started, self.stopped, self.hung = list(outputs), [], [], False
        sweeps = self

        class Fake:
            def __init__(self, workspace: str) -> None:
                sweeps.started.append(workspace)
                self.code, self.text = sweeps.outputs.pop(0) if sweeps.outputs else (0, "")

            def done(self) -> int | None:
                return None if sweeps.hung else self.code

            def output(self) -> str:
                return self.text

            def stop(self) -> None:
                sweeps.stopped.append(self)

        monkeypatch.setattr(omnigent_agent, "Sweep", Fake)


def lead(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[base.Lead, Path]:
    """A followed lead whose workspace is a checkout of ``o/r`` on this host, its default branch never moving."""
    registry = base.following(tmp_path)
    og = base.Lead(base.told("brief", 60), base.ending("STILL WORKING: building", 5))
    og.snap = {"status": "idle", "workspace": str(tmp_path)}
    base.in_checkout(og)
    base.github(monkeypatch, [A])
    monkeypatch.setattr(omnigent_agent, "pr_settled", lambda pr, repo="": None)
    return og, registry


def told(og: base.Lead) -> list[str]:
    return [t for t in base.posted(og) if "check stalled" in t or "satisfied verdict" in t]


def test_a_stalled_pr_is_said_once_and_again_only_at_a_new_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og, registry = lead(tmp_path, monkeypatch)
    monkeypatch.setattr(omnigent_agent, "STALLED_SECONDS", 0)
    unjudged = "PR #6 into other is not judged here: gatekeeper.py differs from origin/other's"
    sweeps = Sweeps(
        monkeypatch,
        (1, f"{line(5, A)}\n{unjudged}\nPR #5: risk: low; merge: gates\n"),
        (1, f"{line(5, A)}\n"),  # the hour after: the same PR at the same head
        (1, f"{line(5, B)}\n{line(7, A)}\n"),  # a push to #5, and #7 newly stalled
        (0, ""),
        (1, f"{line(5, B)}\n"),  # #5 left the listing and came back: news again
    )
    # each poll collects the last poll's sweep and starts the next: the fifth is collected by the sixth poll
    base.supervised(og, registry, monkeypatch, 6, notify="cos")
    assert sweeps.started == [str(tmp_path)] * 6
    assert told(og) == [
        f"Supervisor: o/r: {line(5, A)}: land it (`land 5 --only`) or flag it",
        f"Supervisor: o/r: {line(5, B)}: land it (`land 5 --only`) or flag it",
        f"Supervisor: o/r: {line(7, A)}: land it (`land 7 --only`) or flag it",
        f"Supervisor: o/r: {line(5, B)}: land it (`land 5 --only`) or flag it",
    ]


def test_a_sweep_runs_at_most_once_an_hour(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    og, registry = lead(tmp_path, monkeypatch)
    sweeps = Sweeps(monkeypatch, (1, f"{line(5, A)}\n"))
    base.supervised(og, registry, monkeypatch, 6, notify="cos")
    assert sweeps.started == [str(tmp_path)]
    assert len(told(og)) == 1


def test_a_hung_sweep_is_stopped_and_a_failed_one_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og, registry = lead(tmp_path, monkeypatch)
    monkeypatch.setattr(omnigent_agent, "STALLED_SECONDS", 0)
    monkeypatch.setattr(omnigent_agent, "STALLED_TIMEOUT", -1)
    sweeps = Sweeps(monkeypatch, (2, "could not fetch main\n"))
    sweeps.hung = True
    base.supervised(og, registry, monkeypatch, 3, notify="cos")
    assert (
        len(sweeps.stopped) == 2 and told(og) == []
    )  # three polls: each later one stops the last and starts again
    assert "o/r: check stalled ran past -1s: stopped" in capsys.readouterr().err
    sweeps.hung, sweeps.outputs = False, [(2, "could not fetch main\n")]
    monkeypatch.setattr(omnigent_agent, "STALLED_TIMEOUT", 900)
    base.supervised(og, registry, monkeypatch, 3, notify="cos")
    assert "o/r: check stalled exited 2: could not fetch main" in capsys.readouterr().err
    assert told(og) == []


def test_a_lead_on_another_host_or_with_no_checkout_is_not_swept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og, registry = lead(tmp_path, monkeypatch)
    sweeps = Sweeps(monkeypatch)
    og.snap["host_id"] = "far"
    base.supervised(og, registry, monkeypatch, 3, notify="cos")
    og.snap = {"status": "idle", "workspace": str(tmp_path / "gone")}
    base.supervised(og, registry, monkeypatch, 3, notify="cos")
    assert sweeps.started == []


def test_the_console_routes_a_stalled_pr_to_the_chief_of_staff_once_across_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og, registry = lead(tmp_path, monkeypatch)
    monkeypatch.setattr(omnigent_agent, "STALLED_SECONDS", 0)
    Sweeps(monkeypatch, (1, f"{line(5, A)}\n"), (1, f"{line(5, A)}\n"))
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    events = [e for e in base.events_of(registry) if e["id"].startswith("stalled:")]
    assert [(e["id"], e["settled"], e["action"]) for e in events] == [
        ("stalled:o/r#5:" + A, "rule", "act")
    ]
    assert base.state_of(registry)["stalled"] == {"o/r": {"5": A}}
    Sweeps(monkeypatch, (1, f"{line(5, A)}\n"))  # a restarted supervisor reads the state back
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert len([e for e in base.events_of(registry) if e["id"].startswith("stalled:")]) == 1


def test_route_settles_a_stalled_event_with_the_chief_of_staff() -> None:
    assert omnigent_agent.route({"kind": "stalled", "line": "x"}, lambda: ("none", "")) == (
        "rule",
        "act",
        "an approved, verified PR its queue never took: land it or flag it",
    )


def test_an_unjudged_pr_is_never_posted_and_keeps_what_was_listed_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#5 is listed, then skipped by a sweep that couldn't judge it, then listed again at the same head: said once;
    the skip goes to the log, never to the notified session."""
    og, registry = lead(tmp_path, monkeypatch)
    monkeypatch.setattr(omnigent_agent, "STALLED_SECONDS", 0)
    skip = "PR #5 into main is not judged here: a refused read"
    Sweeps(
        monkeypatch,
        (1, f"{line(5, A)}\n{line(7, A)}\n"),
        (1, f"{skip}\n{line(7, A)}\n1 of 2 open PRs not judged here\n"),
        (1, f"{line(5, A)}\n{line(7, A)}\n"),
    )
    base.supervised(og, registry, monkeypatch, 4, notify="cos")
    assert [t for t in base.posted(og) if "not judged" in t] == []
    assert told(og) == [
        f"Supervisor: o/r: {line(5, A)}: land it (`land 5 --only`) or flag it",
        f"Supervisor: o/r: {line(7, A)}: land it (`land 7 --only`) or flag it",
    ]
    assert "o/r: PR #5 is not judged here: a refused read" in capsys.readouterr().err


def test_a_sweep_that_judged_no_pr_is_said_once_per_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkout whose gatekeeper differs from the base's judges nothing: its silence is not "nothing stalled"."""
    og, registry = lead(tmp_path, monkeypatch)
    monkeypatch.setattr(omnigent_agent, "STALLED_SECONDS", 0)
    drift = "gatekeeper.py differs from origin/main's: a PR's own copy would judge it"
    blind = f"PR #5 into main is not judged here: {drift}\nPR #7 into main is not judged here: {drift}\n"
    Sweeps(
        monkeypatch,
        (0, blind + "2 of 2 open PRs not judged here\n"),
        (0, blind + "2 of 2 open PRs not judged here\n"),  # the same reason: said already
        (0, ""),  # judged again: the next blind sweep is news
        (0, blind + "2 of 2 open PRs not judged here\n"),
        (0, f"PR #5 into main is not judged here: {drift}\n1 of 2 open PRs not judged here\n"),
    )
    base.supervised(og, registry, monkeypatch, 6, notify="cos")
    said = f"Supervisor: o/r: check stalled judged none of its 2 open PRs: {drift}"
    assert told(og) == [said, said]


def test_no_sweep_starts_while_github_s_rate_limit_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og, registry = lead(tmp_path, monkeypatch)
    sweeps = Sweeps(monkeypatch)

    def limited(*args: str, timeout: float = 0) -> str:
        raise omnigent_agent.RateLimited("API rate limit exceeded", 3600)

    monkeypatch.setattr(omnigent_agent, "gh", limited)
    base.supervised(og, registry, monkeypatch, 3, notify="cos")
    assert sweeps.started == []


@pytest.mark.parametrize("flags", ["\tdirect", ""], ids=["direct", "not followed"])
def test_a_direct_or_unfollowed_lead_is_not_swept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: str
) -> None:
    og, registry = lead(tmp_path, monkeypatch)
    text = registry.read_text()
    registry.write_text(text.rstrip("\n") + flags + "\n" if flags else text.replace("\tfollow", ""))
    sweeps = Sweeps(monkeypatch)
    base.supervised(og, registry, monkeypatch, 3, notify="cos")
    assert sweeps.started == []


def test_the_real_sweep_runs_the_installed_check_detached_and_is_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Sweep`` itself, on a stand-in gatekeeper.py: it runs in the workspace, its output is read once it ends,
    and ``stop`` kills one that hangs."""
    if not omnigent_agent.shutil.which("uv"):
        pytest.skip("uv is not installed")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "gatekeeper.py").write_text(
        "import os, sys, time\n"
        "if os.path.exists('hang'):\n    time.sleep(60)\n"
        f"print('{line(5, A)}', flush=True)\nprint(os.getcwd(), file=sys.stderr)\nsys.exit(1)\n"
    )
    monkeypatch.setattr(
        omnigent_agent, "installed", lambda skill: scripts if skill == "gatekeeper" else None
    )
    work = tmp_path / "work"
    work.mkdir()
    sweep = omnigent_agent.Sweep(str(work))
    sweep.proc.wait(timeout=60)
    assert sweep.done() == 1
    assert sweep.output().splitlines() == [line(5, A), str(work)]
    (work / "hang").write_text("")
    hung = omnigent_agent.Sweep(str(work))
    assert hung.done() is None
    hung.stop()
    assert hung.done() is not None


def test_a_sweep_without_the_installed_check_does_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(omnigent_agent, "installed", lambda skill: None)
    with pytest.raises(omnigent_agent.Fail, match="not installed"):
        omnigent_agent.Sweep(".")
