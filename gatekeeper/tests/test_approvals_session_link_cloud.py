"""A cloud lead has no server variables, so the `Owner:` record takes its session link from the one it was given (#2495)."""

from __future__ import annotations

import pytest
from approvals_harness import approvals
from test_approvals_owner_record import LINK, build, owner_notes, posted  # noqa: F401


@pytest.fixture(autouse=True)
def cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNNER_SERVER_URL", raising=False)
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", raising=False)


def test_a_cloud_run_with_no_server_variables_writes_the_link_from_its_brief(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    monkeypatch.setenv("OMNIGENT_SESSION_LINK", LINK + "/")
    assert build(monkeypatch) == 0
    assert owner_notes(posted) == [f"Owner: {LINK}\n"]


@pytest.mark.parametrize(
    "given",
    [
        "",
        "lead-session",
        "not a link /c/x",
        "https://example.test/x",
        "https://example.test/c/id?token=abc",  # a query string would reach a public comment
        "https://user:pw@example.test/c/id",  # so would credentials
        "https://example.test/c/id#frag",
    ],
)
def test_a_value_that_is_not_a_session_link_names_no_session(
    monkeypatch: pytest.MonkeyPatch, given: str
) -> None:
    monkeypatch.setenv("OMNIGENT_SESSION_LINK", given)
    assert approvals.session_link() is None


def test_the_given_link_wins_over_the_server_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runner's primary session is the root of the tree: a lead started under a manager must name itself (#2583)."""
    monkeypatch.setenv("RUNNER_SERVER_URL", "https://a.test")
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "root")
    monkeypatch.setenv("OMNIGENT_SESSION_LINK", LINK)
    assert approvals.session_link() == LINK


def test_a_malformed_given_link_falls_back_to_the_server_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNNER_SERVER_URL", "https://a.test")
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "root")
    monkeypatch.setenv("OMNIGENT_SESSION_LINK", "https://example.test/c/id?token=abc")
    assert approvals.session_link() == "https://a.test/c/root"
