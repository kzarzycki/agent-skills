"""approvals.py: a verdict from a fallback verifier (Gemini through agy, or same-family) never lands a high-risk change (#890, #609),
unless the policy's dated `risk.lower_tier_until` is live (#1088)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from approvals_harness import (
    HEAD,
    add,
    added,  # noqa: F401
    approvals,
    approved,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    lands,  # noqa: F401
    loop_md,
    others_open,  # noqa: F401
    pull,
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
    verdict_on,
    writers,  # noqa: F401
)

OWNED = ("approved:merge",)


@pytest.mark.parametrize(
    "family",
    ["agy/gemini-4-hydrogen-medium/?", "agy", "gemini-4", "claude, same-family"],
)
def test_a_fallback_verdict_lands_low_risk_and_never_high(
    monkeypatch: pytest.MonkeyPatch, family: str
) -> None:
    monkeypatch.setattr(approvals, "writer", lambda _login: False)
    judged = add(loop_md("spec:\n  auto: true\n"), "risk", "verifier: true\n")

    def gate(risk: str) -> list[str]:
        heading = f"Verifier ({family}), pass 1"
        review = verdict_on(HEAD, "0 blocker, 0 major, 0 minor", heading=heading) | {
            "body": f"{heading} on {HEAD[:7]}.\n\nVERDICT: 0 blocker, 0 major, 0 minor\nSATISFIED: yes\nRisk: {risk}\n"
        }
        return approvals.proofs(
            "merge",
            pull(reviews=[review], labels=OWNED),
            [approved(1, "kind:bug", "area:web")],
            judged,
        )

    assert gate("low — a fixture") == []
    assert "lower tier" in gate("high — CI permissions")[0]


def test_a_codex_family_naming_no_fallback_is_the_default_tier() -> None:
    def said(family: str) -> list[tuple[str, int, dict[str, str]]]:
        return [(HEAD, 1, {"Family": family})]

    assert approvals.lower(said("codex/terra-6.1/med")) is None
    assert approvals.lower(said("agy/gemini-4-argon-high/?")) == "agy"
    assert approvals.lower(said("claude, same-family")) == "same-family"


TODAY = date(2026, 11, 18)


def high_risk_gate(family: str, policy: str, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """check merge's findings for a satisfied `family` verdict that rates the PR high, under `policy`'s risk section
    (verifier: true and whatever else it adds), on TODAY in UTC."""
    monkeypatch.setattr(approvals, "writer", lambda _login: False)
    monkeypatch.setattr(approvals, "today", lambda: TODAY)
    heading = f"Verifier ({family}), pass 1"
    review = verdict_on(HEAD, "0 blocker, 0 major, 0 minor", heading=heading) | {
        "body": f"{heading} on {HEAD[:7]}.\n\nVERDICT: 0 blocker, 0 major, 0 minor\nSATISFIED: yes\nRisk: high — a gate\n"
    }
    return approvals.proofs(
        "merge",
        pull(reviews=[review], labels=OWNED),
        [approved(1, "kind:bug", "area:web")],
        add(loop_md("spec:\n  auto: true\n"), "risk", "verifier: true\n" + policy),
    )


@pytest.mark.parametrize("until", ["2026-11-20", "2026-11-18"])
def test_a_live_lower_tier_until_lands_a_high_risk_pr_on_a_fallback_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], until: str
) -> None:
    assert high_risk_gate("claude, same-family", f"lower_tier_until: {until}\n", monkeypatch) == []
    said = capsys.readouterr().out
    assert "lower tier (same-family)" in said and f"risk.lower_tier_until: {until}" in said


def test_a_past_lower_tier_until_refuses_again_and_says_it_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = high_risk_gate(
        "agy/gemini-4-hydrogen-medium/?", "lower_tier_until: 2026-11-17\n", monkeypatch
    )
    assert len(found) == 1
    assert (
        "lower tier (agy)" in found[0]
        and "`risk.lower_tier_until: 2026-11-17` has passed" in found[0]
    )


def test_without_lower_tier_until_a_fallback_verdict_never_lands_high_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = high_risk_gate("claude/sonnet-5.5 mid", "", monkeypatch)
    assert len(found) == 1 and "lower tier (mid)" in found[0] and "has passed" not in found[0]


@pytest.mark.parametrize(
    "policy", ["", "lower_tier_until: 2026-11-17\n", "lower_tier_until: 2026-11-20\n"]
)
def test_a_default_tier_verdict_is_unaffected_by_lower_tier_until(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], policy: str
) -> None:
    assert high_risk_gate("codex/sol-6.1/high", policy, monkeypatch) == []
    assert "lower_tier_until" not in capsys.readouterr().out


@pytest.mark.parametrize("value", ['"2026-11-20"', "2026-11-20T05:47:00Z", "20261120", "true"])
def test_lower_tier_until_must_be_an_unquoted_date(value: str) -> None:
    with pytest.raises(approvals.Refused, match=r"`risk\.lower_tier_until` must be a date"):
        approvals.settings(add(loop_md(), "risk", f"lower_tier_until: {value}\n"))


def test_today_is_the_utc_date() -> None:
    assert approvals.today() == datetime.now(UTC).date()
