"""approvals.py: loop.md's `verifier.same_family` caps the risk at which a same-family verdict lands, and
`same_family_until` lifts it until a date (#609)."""

from __future__ import annotations

import pytest
from approvals_harness import (
    HEAD,
    add,
    approvals,
    approved,
    lands,  # noqa: F401
    loop_md,
    pull,
    verdict_on,
    writers,  # noqa: F401
)

SAME = "claude, same-family"


def with_setting(
    setting: str,
    family: str | tuple[str, ...],
    risk: str,
    monkeypatch: pytest.MonkeyPatch,
    body: str = "## Evidence\n\nlog line\n",
) -> list[str]:
    """proofs() of a satisfied verdict from each family named (two make a mixed pass), under loop.md's `verifier`
    section `setting` (none when empty)."""
    monkeypatch.setattr(approvals, "writer", lambda _login: False)
    judged = add(loop_md("spec:\n  auto: true\n"), "risk", "verifier: true\n")
    if setting:
        judged = add(judged, "verifier", setting)
    reviews = []
    for one in (family,) if isinstance(family, str) else family:
        heading = f"Verifier ({one}), pass 1"
        reviews.append(
            verdict_on(HEAD, "0 blocker, 0 major, 0 minor", heading=heading)
            | {
                "body": f"{heading} on {HEAD[:7]}.\n\nVERDICT: 0 blocker, 0 major, 0 minor\nSATISFIED: yes\nRisk: {risk}\n"
            }
        )
    return approvals.proofs(
        "merge",
        pull(reviews=tuple(reviews), labels=("approved:merge",), body=body),
        [approved(1, "kind:bug", "area:web")],
        judged,
    )


def test_never_refuses_a_same_family_verdict_even_on_a_low_risk_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = with_setting("same_family: never\n", SAME, "low", monkeypatch)
    assert any("verifier.same_family: never" in line for line in found)


def test_low_lands_a_low_risk_change_and_refuses_a_high_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert with_setting("same_family: low\n", SAME, "low", monkeypatch) == []
    found = with_setting("same_family: low\n", SAME, "high — CI permissions", monkeypatch)
    assert any("verifier.same_family: low" in line for line in found)


def test_high_lands_a_high_risk_change(monkeypatch: pytest.MonkeyPatch) -> None:
    assert with_setting("same_family: high\n", SAME, "high — CI permissions", monkeypatch) == []


def test_another_family_is_never_held(monkeypatch: pytest.MonkeyPatch) -> None:
    assert with_setting("same_family: never\n", "codex/terra-6.1/med", "low", monkeypatch) == []


def test_an_expired_until_falls_back_to_the_base_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    setting = "same_family: never\nsame_family_until: '2000-01-01'\n"
    found = with_setting(setting, SAME, "low", monkeypatch)
    assert any("verifier.same_family: never" in line for line in found)


def test_a_current_until_lets_the_verdict_land(monkeypatch: pytest.MonkeyPatch) -> None:
    setting = "same_family: never\nsame_family_until: '2099-01-01'\n"
    assert with_setting(setting, SAME, "high — CI permissions", monkeypatch) == []


def test_no_setting_is_never(monkeypatch: pytest.MonkeyPatch) -> None:
    """#609 F1: the default is `never`, so an unset ceiling refuses a same-family verdict, whatever the risk."""
    for risk in ("low", "high — CI permissions"):
        found = with_setting("", SAME, risk, monkeypatch)
        assert any("verifier.same_family: never" in line for line in found)


def test_an_unmarked_verdict_of_the_authors_family_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    """#609 F2: the PR body's `Impl:` family decides, so a heading with no `same-family` marker is still held."""
    body = "## Evidence\n\nlog line\n\nImpl: cc/sonnet-5.5/? · Session: https://x/c/1\n"
    found = with_setting("same_family: never\n", "claude/sonnet/?", "low", monkeypatch, body)
    assert any("verifier.same_family: never" in line for line in found)
    assert (
        with_setting("same_family: never\n", "codex/terra-6.1/med", "low", monkeypatch, body) == []
    )


def test_an_unmarked_verdict_lands_when_the_author_family_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert with_setting("same_family: never\n", "claude/sonnet/?", "low", monkeypatch) == []


def test_an_agent_author_of_unknown_harness_holds_every_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#609 F2: an `Impl:` line whose harness is `?` names an agent, so no verdict is shown independent of it; only a
    PR with no `Impl:` line (a person's) lets an unmarked verdict of a known family land."""
    body = "## Evidence\n\nlog line\n\nImpl: ?/sonnet-5.5/? · Session: https://x/c/1\n"
    for family in ("claude/sonnet/?", "codex/terra-6.1/med"):
        found = with_setting("same_family: never\n", family, "low", monkeypatch, body)
        assert any("verifier.same_family: never" in line for line in found)


def test_a_verdict_naming_no_family_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    found = with_setting(
        "same_family: never\n", ("claude, same-family", "unknown"), "low", monkeypatch
    )
    assert any("verifier.same_family: never" in line for line in found)


def test_a_pass_with_a_verdict_of_another_family_is_not_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mixed = (SAME, "codex/terra-6.1/med")
    assert with_setting("same_family: never\n", mixed, "low", monkeypatch) == []


@pytest.mark.parametrize("until", ["tomorrow", "20990101", "2099-13-45", "2099-1-1"])
@pytest.mark.parametrize("ceiling", ["", "same_family: never\n"])
def test_a_malformed_until_is_refused_when_the_policy_loads(
    monkeypatch: pytest.MonkeyPatch, until: str, ceiling: str
) -> None:
    """#609 F3: whatever the verdict's family, so a typo is reported before it affects a PR."""
    setting = f"{ceiling}same_family_until: '{until}'\n"
    with pytest.raises(approvals.Refused, match="same_family_until"):
        with_setting(setting, "codex/terra-6.1/med", "low", monkeypatch)
