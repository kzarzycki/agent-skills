"""Two supervisors read one merge-queue comment; only the team that holds queue duty raises its project-wide events
(#2500). The duty is gatekeeper.md's `queue_duty` section; a project without one raises as before.

The seam: the same faked ``gh`` and Omnigent fleet as the dequeue tests, and the real gatekeeper module with its base
policy and account faked, so the supervisor reads the setting as it would in a checkout."""

from __future__ import annotations

import pytest
from test_omnigent_agent import events_of
from test_omnigent_queue_rejects import GitHub, comment, fleet, log_of, omnigent_agent, run


def policy(*lines: str) -> str:
    return "# Gatekeeper\n\n## Policy\n\n```yaml\n" + "\n".join(lines) + "\n```\n"


def supervisor_of(monkeypatch: pytest.MonkeyPatch, text: str | None, account: str = "ci") -> None:
    """The supervisor runs in a checkout whose default branch holds ``text`` as gatekeeper.md, as ``account``."""
    gk = omnigent_agent._load_gatekeeper()
    assert gk is not None
    monkeypatch.setattr(omnigent_agent, "_load_gatekeeper", lambda: gk)
    monkeypatch.setattr(gk, "toplevel", lambda: ".")
    monkeypatch.setattr(gk, "default_base", lambda root: "main")
    monkeypatch.setattr(
        gk, "base_policy", lambda base, checkout: gk.Policy(text) if text is not None else None
    )
    monkeypatch.setattr(gk, "viewer", lambda: account)


def flake_kinds(tmp_path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The kinds of event one supervisor raises on the merge queue's comments: one test failing the runs of two PRs."""
    registry, og = fleet(tmp_path)
    og.snaps["a"] = {"labels": {"omni.role": "lead"}}
    gh = GitHub(monkeypatch)
    gh.comments += [comment(100, 12, jobs=(7,)), comment(101, 13, jobs=(8,))]
    gh.logs.update({7: log_of("t::flaky"), 8: log_of("t::flaky")})
    run(og, registry, monkeypatch, 3)
    return [e["kind"] for e in events_of(registry) if e["kind"].startswith("queue-")]


DUTY = policy("team:", "  name: alpha", "queue_duty:", "  team: alpha")


def test_only_the_team_that_holds_queue_duty_raises_the_flake(tmp_path, monkeypatch) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    supervisor_of(monkeypatch, DUTY)
    assert flake_kinds(tmp_path / "alpha", monkeypatch) == ["queue-flake"]
    supervisor_of(monkeypatch, policy("team:", "  name: beta", "queue_duty:", "  team: alpha"))
    assert flake_kinds(tmp_path / "beta", monkeypatch) == []


def test_the_account_names_a_team_that_sets_no_name(tmp_path, monkeypatch) -> None:
    (tmp_path / "x").mkdir()
    supervisor_of(monkeypatch, policy("queue_duty:", "  team: alpha"), account="alpha")
    assert flake_kinds(tmp_path / "x", monkeypatch) == ["queue-flake"]


@pytest.mark.parametrize("text", [None, policy("team: {}"), policy("loop:", "  cap: 3")])
def test_a_project_without_the_setting_raises_as_before(tmp_path, monkeypatch, text) -> None:
    supervisor_of(monkeypatch, text)
    assert flake_kinds(tmp_path, monkeypatch) == ["queue-flake"]


def test_an_unreadable_policy_raises_as_before(tmp_path, monkeypatch) -> None:
    supervisor_of(monkeypatch, policy("queue_duty:", "  team: [not, a, name]"))
    assert flake_kinds(tmp_path, monkeypatch) == ["queue-flake"]
