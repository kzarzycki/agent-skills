"""omnigent_agent.py: a loop session carries its phase as `omni.phase` beside `omni.role` and `omni.pr`, so the
telemetry stack groups per-PR spend by phase (#945)."""

from pathlib import Path

import test_omnigent_agent as base  # the faked server; Posting's sessions come from the real create
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent


def labels(og: base.Posting) -> dict:
    return og.bodies[-1].get("labels", {})


def test_a_verifier_carries_its_pr_and_the_verify_phase(tmp_path: Path) -> None:
    og = base.Posting()
    omnigent_agent.start(
        og,
        "codex",
        "t",
        "do X",
        tmp_path / "r.md",
        "/x/engineering-loop/verifier.md",
        0,
        about=omnigent_agent.pr_ref("o/r#9"),
    )
    assert labels(og) == {"omni.role": "verifier", "omni.phase": "verify", "omni.pr": "o/r#9"}


def test_a_worker_carries_the_build_phase(tmp_path: Path) -> None:
    og = base.Posting()
    omnigent_agent.start(
        og, "claude-cloud", "t", "do X", tmp_path / "r.md", "/x/engineering-loop/worker.md", 0
    )
    assert labels(og)["omni.phase"] == "build"


def test_a_session_with_no_loop_role_has_no_phase(tmp_path: Path) -> None:
    og = base.Posting()
    omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
    assert "omni.phase" not in labels(og)
