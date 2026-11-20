"""omnigent_agent.py: a lead's delegation text from the base policy, and a USER NEEDED with no card (#1551)."""

import subprocess
from pathlib import Path

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import (  # noqa: F401  (the fixtures apply here by name)
    Lead,
    ending,
    following,
    no_model,
    no_sleep,
    posted,
    supervised,
    told,
)

omnigent_agent = base.omnigent_agent

POLICY = "docs/agents/gatekeeper.md"


def checkout(tmp_path: Path, policy: str | None) -> Path:
    """A checkout whose `origin/main` holds ``policy`` as its gatekeeper.md (none: no policy file)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True
        )

    (work / "README.md").write_text("x\n")
    if policy is not None:
        (work / POLICY).parent.mkdir(parents=True)
        (work / POLICY).write_text(policy)
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    git("remote", "add", "origin", str(origin))
    git("push", "-q", "origin", "main")
    git("fetch", "-q", "origin")
    git("remote", "set-head", "origin", "main")
    return work


def policy_with(loop: str) -> str:
    return f"# Gatekeeper\n\n## Policy\n\n```yaml\n{loop}```\n"


@pytest.mark.parametrize(
    ("policy", "delegated"),
    [
        (policy_with("loop:\n  delegate: all\n"), True),
        (policy_with("loop:\n  delegate: feature\n"), False),
        (policy_with("loop:\n  gate: mise run check\n"), False),
        (None, False),
    ],
)
def test_the_delegation_text_follows_the_base_policy(
    tmp_path: Path, policy: str | None, delegated: bool
) -> None:
    work = checkout(tmp_path, policy)
    text = omnigent_agent.lead_delegation(str(work), False)
    assert text == (omnigent_agent.DELEGATION if delegated else "")


def test_the_text_names_the_merge_go_and_the_critical_paths() -> None:
    text = omnigent_agent.DELEGATION
    assert "approve merge <pr> --head <sha> --by delegate" in text
    assert "risk:high" in text and "risk.critical_paths" in text and "sys_ask_user_question" in text
    gk = omnigent_agent._load_gatekeeper()
    assert gk is not None  # the flags are those gatekeeper's `approve` takes
    src = Path(gk.__file__).read_text()
    assert 'choices=("owner", DELEGATE)' in src and 'approving.add_argument("--head")' in src


def test_a_top_level_lead_start_carries_the_text_only_under_delegate_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    for policy, delegated in ((policy_with("loop:\n  delegate: all\n"), True), (None, False)):
        work = checkout(tmp_path / str(delegated), policy)
        report = tmp_path / f"{delegated}.md"
        omnigent_agent.start(
            base.FakeOmnigent(),
            "claude",
            "t",
            "do X",
            report,
            None,
            0,
            top_level=True,
            workspace=str(work),
        )
        plain = omnigent_agent.LEAD_PREAMBLE.format(report=report, role="")
        if delegated:
            plain = (
                omnigent_agent.LEAD_PREAMBLE.removesuffix("\n") + omnigent_agent.DELEGATION + "\n"
            )
            plain = plain.format(report=report, role="")
        assert Path(f"{report}.brief").read_text() == "AGENT_SIGNATURE=cc/?/?\n" + plain + "do X"


def test_a_missing_or_broken_policy_reader_gives_todays_wording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = checkout(tmp_path, policy_with("loop:\n  delegate: all\n"))
    monkeypatch.setattr(omnigent_agent, "_load_gatekeeper", lambda: None)
    assert omnigent_agent.lead_delegation(str(work), False) == ""

    class Broken:
        @staticmethod
        def default_base(_: str) -> str:
            raise RuntimeError("boom")

        toplevel = default_base

    monkeypatch.setattr(omnigent_agent, "_load_gatekeeper", lambda: Broken)
    assert omnigent_agent.lead_delegation(str(work), False) == ""


def test_a_workspace_on_another_host_keeps_todays_wording_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert omnigent_agent.lead_delegation(str(tmp_path), True) == ""
    assert "another host" in capsys.readouterr().err


def test_the_cloud_swaps_still_apply_to_a_delegating_lead_preamble() -> None:
    lead = omnigent_agent.LEAD_PREAMBLE.removesuffix("\n") + omnigent_agent.DELEGATION + "\n"
    cloud = omnigent_agent.cloud_preamble(lead, None)
    assert "Your files stay in this cloud VM" in cloud and "--by delegate" in cloud


CARD = {"elicitation_id": "question_1", "params": {"message": "Land it?"}}


@pytest.mark.parametrize(
    ("snap", "line"),
    [({}, omnigent_agent.UNASKED_LINE), ({"pending_elicitations": [CARD]}, "turn ended")],
)
def test_user_needed_with_no_card_is_its_own_event_and_with_one_it_is_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, snap: dict, line: str
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("USER NEEDED: land it?", 1))
    og.snap = snap
    supervised(og, registry, monkeypatch, 3, notify="cos")
    news = [p for p in posted(og) if "asked its user" not in p]  # a card is told once, as before
    assert news == [f"Supervisor: a t-a: {line}\nlast message: USER NEEDED: land it?"]


def test_the_unasked_kind_routes_as_a_user_needed_turn_end_does() -> None:
    event = {"kind": omnigent_agent.UNASKED, "line": "a: x", "last": "USER NEEDED: q"}
    plain = {**event, "kind": "ended"}
    got = omnigent_agent.route(event, lambda: ("owner", ""))
    assert got == omnigent_agent.route(plain, lambda: ("owner", "")) and got[1] == "owner"
