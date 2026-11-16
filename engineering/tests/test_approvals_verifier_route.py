"""approvals.py: a verdict from a fallback verifier (Gemini through agy, or same-family) never lands a high-risk change (#890, #609)."""

from __future__ import annotations

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
