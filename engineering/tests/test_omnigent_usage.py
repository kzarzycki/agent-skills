"""omnigent_agent.py ``usage``: a lead's session tree's tokens and cost for its PR body (#1127)."""

from pathlib import Path

import pytest
import test_omnigent_agent as base  # the module under test, its fixtures
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent


def used(tokens: int, usd: float) -> dict:
    return {"m": {"total_tokens": tokens, "total_cost_usd": usd}}


class Records:
    """Session records by id (``usage_by_model``, ``total_cost_usd``, ``title``) and the live
    children each lists; an id missing from ``records`` is not read."""

    def __init__(self, records: dict[str, dict], children: dict[str, list[str]]) -> None:
        self.records, self.kids, self.reads = records, children, []

    def info(self, sid: str) -> dict:
        self.reads.append(sid)
        if sid not in self.records:
            raise omnigent_agent.Fail(f"GET /v1/sessions/{sid}: HTTP 404")
        return self.records[sid]

    def children(self, sid: str) -> list[str]:
        return self.kids.get(sid, [])

    def session_id(self, sid: str) -> str:
        return sid


def lead_tree() -> Records:
    """A lead with one live worker, an archived verifier the lead names, and a cloud session
    Omnigent recorded no usage for."""
    return Records(
        {
            "lead": {
                "title": "lead",
                "usage_by_model": used(2_000_000, 1.5),
                "total_cost_usd": 1.5,
            },
            "worker": {"usage_by_model": used(500_000, 0.25), "total_cost_usd": 0.25},
            "verifier": {"archived": True, "usage_by_model": used(300_000, 0.75)},
            "cloud": {"title": "cloud worker", "usage_by_model": {}, "total_cost_usd": 0},
        },
        {"lead": ["worker", "cloud"]},
    )


def test_a_lead_its_live_children_and_a_named_archived_one_are_summed_once() -> None:
    og = lead_tree()
    lines = omnigent_agent.spent(og, ["lead", "verifier", "worker"])  # worker named twice
    assert lines == [
        "lead lead: 2.0M tokens, $1.50",
        "verifier: 0.3M tokens, $0.75",
        "worker: 0.5M tokens, $0.25",
        "cloud cloud worker: uncounted (no usage recorded)",
        "Tokens spent: 2.8M, $2.50 (3 sessions; uncounted: cloud)",
    ]
    assert sorted(og.reads) == ["cloud", "lead", "verifier", "worker"]  # each record read once


def test_a_session_not_read_is_uncounted_naming_why() -> None:
    og = Records({"lead": {"usage_by_model": used(50_000, 0.1)}}, {})
    assert omnigent_agent.spent(og, ["lead", "gone"]) == [
        "lead: 50k tokens, $0.10",
        "gone: uncounted (not read: GET /v1/sessions/gone: HTTP 404)",
        "Tokens spent: 50k, $0.10 (1 session; uncounted: gone)",
    ]


def test_the_command_adds_the_session_it_runs_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = lead_tree()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda *a: og)
    monkeypatch.setenv("OMNIGENT_SESSION_ID", "lead")
    assert omnigent_agent.main(["usage", "verifier"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == (
        "Tokens spent: 2.8M, $2.50 (3 sessions; uncounted: cloud)"
    )


def test_the_lead_writes_its_estimate_on_the_draft_pr_and_the_actual_at_landing() -> None:
    lead = (Path(__file__).parents[1] / "skills" / "engineering-loop" / "lead.md").read_text()
    lead = " ".join(lead.split())
    build, land = lead.index("3. **Branch and notes.**"), lead.index("8. **Land**")
    assert build < lead.index("`Token estimate: ~<N> (<basis>)`") < lead.index("4. **Build.**")
    spent = lead.index("`Tokens spent:` line")
    assert land < spent < lead.index("9. **Accept.**")
    assert "omnigent_agent.py usage <session>..." in lead[spent:]
    assert "model and session id of each agent" in lead
