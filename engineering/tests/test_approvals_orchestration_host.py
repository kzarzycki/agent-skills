"""approvals.py on a host marked orchestration-only: every verb that runs the gate refuses, spawning nothing (#1651)."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import SCRIPTS, approvals

REASON = "orchestration host: heavy runs go to the cloud"


@pytest.fixture
def marked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "orchestration-only"
    path.write_text(f"\n{REASON}\nmore\n")
    monkeypatch.setenv("AGENT_ORCHESTRATION_ONLY", str(path))
    return path


@pytest.fixture
def unmarked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ORCHESTRATION_ONLY", str(tmp_path / "none"))


@pytest.fixture
def nothing_spawns(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("ran")

    monkeypatch.setattr(approvals.subprocess, "Popen", boom)
    for name in ("local_ci", "detach", "affected_tests", "run_heavy", "heavy"):
        monkeypatch.setattr(approvals, name, boom)
    monkeypatch.setattr(approvals, "one_repo", lambda: None)


def said(refusal: str) -> None:
    assert "orchestration-only" in refusal and REASON in refusal
    assert "~/.agents/orchestration-only" in refusal
    assert (
        "claude-cloud-run" in refusal
        and "in a cloud session, run this same command there" in refusal
    )
    assert "LOOP_HOST_RUN" in refusal and "Never start a child session" in refusal


def test_run_heavy_refuses_on_a_marked_host_before_it_spawns(
    marked: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("spawned")

    monkeypatch.setattr(approvals.subprocess, "Popen", boom)
    with pytest.raises(approvals.Refused) as refused:
        approvals.run_heavy(["mise", "run", "check-fast"])
    said(str(refused.value))
    assert "`mise run check-fast` refused" in str(refused.value)
    with pytest.raises(approvals.Refused):
        approvals.heavy(["true"])


@pytest.mark.parametrize(
    "argv",
    [
        ["local-ci", "--record"],
        ["local-ci", "--record", "--base", "abc"],
        ["local-ci", "7", "--run"],
        ["record", "checks", "--record"],
        ["affected-tests"],
        ["affected-tests", "--base", "abc"],
        ["heavy", "mise", "run", "check"],
    ],
)
def test_each_gate_verb_refuses_on_a_marked_host(
    marked: Path, nothing_spawns: None, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert approvals.main(argv) == 1
    out = capsys.readouterr().out
    said(out)
    assert f"`approvals.py {argv[0]}" in out


def test_a_verb_that_runs_nothing_heavy_still_runs_on_a_marked_host(
    marked: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    monkeypatch.setattr(approvals, "leads_its_session", lambda: True)
    monkeypatch.setattr(approvals, "local_ci", lambda *a: calls.append(a) or 0)
    assert approvals.main(["local-ci", "7"]) == 0  # reads and posts the head's pass, runs nothing
    assert calls and calls[0][0] == 7
    assert approvals.main(["heavy", "--plan"]) == 0


def test_an_unmarked_host_runs_the_gate(unmarked: None) -> None:
    assert approvals.host_role.orchestration_only() is None
    assert approvals.run_heavy(["true"])[0] == 0
    approvals.orchestration_refusal("mise run check")  # no refusal


def test_an_empty_marker_still_marks_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "orchestration-only"
    path.write_text("")
    monkeypatch.setenv("AGENT_ORCHESTRATION_ONLY", str(path))
    with pytest.raises(approvals.Refused, match="marked orchestration-only"):
        approvals.run_heavy(["true"])


def test_the_marker_is_read_from_home_by_default(tmp_path: Path) -> None:
    role = approvals.host_role
    assert role.orchestration_only({"HOME": str(tmp_path)}) is None
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "orchestration-only").write_text("x\n")
    assert role.orchestration_only({"HOME": str(tmp_path)}) == "x"
    assert role.orchestration_only({}) is None  # no home to look in


def test_the_shared_module_parses_on_the_oldest_python3_a_consumer_has() -> None:
    """The hook imports it on the consumer's own ``python3`` (macOS ships 3.9)."""
    import ast

    ast.parse((SCRIPTS / "host_role.py").read_text(), feature_version=(3, 9))
