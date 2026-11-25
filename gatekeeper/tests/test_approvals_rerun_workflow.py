"""approvals.py: a rerun record that no workflow can push reads as a setup problem, not a wait (#2473). With
`levels.<level>.rerun` on and CI on, `check merge`, `land` and `check setup` name the missing rerun workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (  # noqa: F401
    TREE,
    approvals,
    gating,
    judged_pr,
    judging,
)
from test_approvals import gatekeeper_md, github, reviewing  # noqa: F401
from test_approvals_rerun import ASKED, GATES, check_merge, forge, policy  # noqa: F401
from test_approvals_setup_check import FENCED, POLICY, repo_with, run_setup

Gate = tuple[dict[str, Any], list[tuple[int, str]]]

MISSING = (
    "`levels.high.rerun` asks an independent rerun, but no workflow under .github/workflows runs"
    " `local-ci --record --rerun` (directly or through a mise task), so the rerun record can't come: add a rerun"
    " workflow, or set `levels.high.rerun: false` in docs/agents/gatekeeper.md"
)
RERUN_FLOW = ".github/workflows/rerun.yml"
STEP = "uv run scripts/approvals.py local-ci --record --rerun"
FLOW = (
    "on: pull_request\njobs:\n  rerun:\n    runs-on: ubuntu-latest\n    steps:\n      - run: %s\n"
)
DIRECT = FLOW % STEP
OTHER_FLOW = FLOW % "uv run scripts/approvals.py local-ci --record"
TASK = f'[tasks."rerun:record"]\nrun = "{STEP}"\n'
WRAPPED = TASK + '[tasks.wrapped]\nrun = "mise run rerun:record"\n'


def write(name: str, text: str) -> None:
    Path(name).parent.mkdir(parents=True, exist_ok=True)
    Path(name).write_text(text)


def refused(gating: Gate) -> None:
    state, _ = gating
    Path(RERUN_FLOW).unlink(missing_ok=True)  # the forge fixture's workflow
    policy(GATES)
    state["pull"] = judged_pr(judging("low — fine"), labels=("risk:high",))


def test_a_missing_rerun_workflow_is_named_with_both_fixes(
    gating: Gate, forge: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    refused(gating)
    write(".github/workflows/other.yml", OTHER_FLOW)  # CI, but nothing that reruns
    code, out = check_merge(capsys)
    assert code == 1
    assert out == [f"{ASKED} origin holds no rerun record on tree {TREE}; {MISSING}"]


@pytest.mark.parametrize(
    "files",
    [
        {RERUN_FLOW: DIRECT},
        {RERUN_FLOW: FLOW % "mise run rerun:record", "mise.toml": TASK},
        {RERUN_FLOW: FLOW % "mise run wrapped", "mise.toml": WRAPPED},
    ],
)
def test_a_workflow_that_reruns_leaves_todays_wait(
    gating: Gate,
    forge: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
) -> None:
    refused(gating)
    for name, text in files.items():
        write(name, text)
    code, out = check_merge(capsys)
    assert code == 1
    assert len(out) == 1
    assert out[0].startswith(f"{ASKED} origin holds no rerun record on tree {TREE}.")
    assert "can't come" not in out[0] and "Where the repo has CI" in out[0]


def test_no_ci_or_rerun_off_changes_nothing(
    gating: Gate, forge: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    refused(gating)
    policy(GATES + "loop:\n  ci: false\n")
    out = check_merge(capsys)[1]
    assert "can't come" not in out[0] and "with no CI, the verifier" in out[0]
    policy(GATES + "    rerun: false\n")
    assert check_merge(capsys) == (0, [])


def test_land_refuses_on_it_without_waiting_on_ci(
    gating: Gate,
    forge: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused(gating)
    state, _ = gating
    monkeypatch.setattr(approvals.time, "sleep", lambda _s: pytest.fail("land waited"))
    tracker, loop = approvals.project()
    verdict = approvals.landable(state["pull"], tracker, loop, {"check"}, named=True)
    # (1, False): a refusal no wait clears, not (WAITING, True), the wait on CI
    assert verdict.exit == (1, False)
    assert MISSING in capsys.readouterr().out


def test_check_setup_warns_for_each_level_with_rerun_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = repo_with(tmp_path, monkeypatch, {POLICY: FENCED})
    code, out = run_setup(capsys)
    assert code == 0 and MISSING in out and "`levels.critical.rerun`" in out
    (repo / RERUN_FLOW).parent.mkdir(parents=True)
    (repo / RERUN_FLOW).write_text(DIRECT)
    code, out = run_setup(capsys)
    assert code == 0 and "can't come" not in out, out
    (repo / RERUN_FLOW).unlink()
    off = "levels:\n  high:\n    rerun: false\n  critical:\n    rerun: false\n"
    (repo / POLICY).write_text(gatekeeper_md(off))
    code, out = run_setup(capsys)
    assert code == 0 and "can't come" not in out, out
