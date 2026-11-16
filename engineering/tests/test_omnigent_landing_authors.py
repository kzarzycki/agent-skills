"""omnigent_agent.py: the supervisor's ``landed`` event counts only merges a followed, non-direct
lead made: a PR the login it runs as opened (#1129)."""

from pathlib import Path

import pytest
import test_omnigent_agent as base  # the faked server, the supervisor loop
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent
OLD, NEW = base.OLD, base.NEW


def github(
    monkeypatch: pytest.MonkeyPatch, head: list[str], authors: dict[str, str | None]
) -> list[tuple[str, ...]]:
    """``gh`` faked: this runs as ``me``; the comparison lists ``authors``' PRs, each opened by its
    login (None: its read fails). Each call is recorded."""
    monkeypatch.setattr(omnigent_agent, "HEAD_SECONDS", 0)
    calls: list[tuple[str, ...]] = []

    def gh(*args: str, timeout: float = 0) -> str:
        calls.append(args)
        if args[1] == "repos/o/r/commits/HEAD":
            return head[0] + "\n"
        if args[1] == "user":
            return "me\n"
        if args[1] == f"repos/o/r/compare/{OLD}...{NEW}":
            return "".join(f"Change (#{n})\n" for n in authors)
        if args[1].startswith("repos/o/r/pulls/"):
            login = authors[args[1].rsplit("/", 1)[1]]
            if login is None:
                raise omnigent_agent.Fail("gh api: HTTP 502")
            return login + "\n"
        raise AssertionError(args)

    monkeypatch.setattr(omnigent_agent, "gh", gh)
    return calls


def moved(og: base.Fleet, registry: Path, monkeypatch: pytest.MonkeyPatch, head: list[str]) -> None:
    base.in_checkout(og)
    base.supervised(
        og, registry, monkeypatch, 2, lambda poll: head.__setitem__(0, NEW), console=True
    )


def test_a_bot_s_merge_alone_raises_nothing_and_stores_the_new_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, head = base.following(tmp_path), [OLD]
    github(monkeypatch, head, {"843": "release-bot[bot]"})
    moved(base.Lead(base.told("brief", 60)), registry, monkeypatch, head)
    assert base.landed(registry) == []
    assert base.state_of(registry)["heads"] == {"o/r": NEW}


def test_a_lead_s_pr_beside_a_bot_s_and_a_teammate_s_is_the_only_one_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, head = base.following(tmp_path), [OLD]
    github(monkeypatch, head, {"843": "release-bot[bot]", "844": "me", "845": "teammate"})
    moved(base.Lead(base.told("brief", 60)), registry, monkeypatch, head)
    (event,) = base.landed(registry)
    assert event["line"].endswith(f"merged since {OLD[:12]}: #844")


def test_a_repo_only_direct_leads_work_in_is_not_watched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, head = base.direct_lead(tmp_path), [OLD]
    calls = github(monkeypatch, head, {"844": "me"})
    moved(base.Lead(base.told("brief", 60)), registry, monkeypatch, head)
    assert calls == [] and base.landed(registry) == []


def test_an_author_not_read_still_raises_the_landing_naming_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, head = base.following(tmp_path), [OLD]
    github(monkeypatch, head, {"843": "release-bot[bot]", "846": None})
    moved(base.Lead(base.told("brief", 60)), registry, monkeypatch, head)
    (event,) = base.landed(registry)
    assert (
        "#846 (author not read: gh api: HTTP 502)" in event["line"] and "#843" not in event["line"]
    )
