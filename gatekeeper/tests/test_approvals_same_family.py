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
from test_approvals_verifier_route import gate

SAME = "claude, same-family"


def with_setting(
    setting: str, family: str, risk: str, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    monkeypatch.setattr(approvals, "writer", lambda _login: False)
    judged = add(loop_md("spec:\n  auto: true\n"), "risk", "verifier: true\n")
    judged = add(judged, "verifier", setting)
    heading = f"Verifier ({family}), pass 1"
    review = verdict_on(HEAD, "0 blocker, 0 major, 0 minor", heading=heading) | {
        "body": f"{heading} on {HEAD[:7]}.\n\nVERDICT: 0 blocker, 0 major, 0 minor\nSATISFIED: yes\nRisk: {risk}\n"
    }
    return approvals.proofs(
        "merge",
        pull(reviews=[review], labels=("approved:merge",)),
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


def test_no_setting_keeps_todays_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    assert gate(SAME, "high — CI permissions", monkeypatch) == []
