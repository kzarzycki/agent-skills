"""R7, after the merge only a tree nobody tested runs (#2179, #2261): the loop's `nightly.py moved` decides, from the
forge, whether the push run on main or the nightly has anything to run, `engineering-ci.yml` calls it, and the skill
text points to the rule instead of restating it."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import urllib.error
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "loop" / "skills" / "engineering-loop"
WORKFLOW = REPOSITORY / ".github" / "workflows" / "engineering-ci.yml"
HEADING = "A check runs only if it can fail because of the change"

sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("nightly_moved", SKILL / "scripts" / "nightly.py")
nightly = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nightly)

MAIN = "a" * 40
BATCH = "b" * 40
OTHER = "c" * 40
MERGIFY = "mergify/merge-queue/x"
GITHUB = "gh-readonly-queue/main/pr-5-" + BATCH


class Forge:
    """A stand-in for the forge's REST API: path -> JSON, the query string ignored."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes

    def __call__(self, path: str):
        return self.routes[path.split("?")[0]]


def runs(*items):
    return {"workflow_runs": list(items)}


def run(branch: str, sha: str, number: int, event: str = "pull_request") -> dict:
    return {
        "id": number,
        "head_branch": branch,
        "head_sha": sha,
        "event": event,
        "html_url": f"https://example.test/runs/{number}",
    }


def forge(batch_tree: str, main_tree: str = "t1", batches=None) -> Forge:
    """Runs by `event=` of the query, as the forge filters them."""
    batches = [run(MERGIFY, BATCH, 7)] if batches is None else batches

    def listing(path: str):
        event = path.split("event=")[1].split("&")[0]
        return runs(*(b for b in batches if b["event"] == event))

    api = Forge(
        {
            f"/repos/o/r/git/commits/{BATCH}": {"tree": {"sha": batch_tree}},
            f"/repos/o/r/git/commits/{MAIN}": {"tree": {"sha": main_tree}},
            f"/repos/o/r/git/commits/{OTHER}": {"tree": {"sha": "t9"}},
        }
    )
    return lambda path: listing(path) if "/runs?" in path else api(path)


def queue_run(queue: str) -> dict:
    return run(MERGIFY, BATCH, 7) if queue == "mergify" else run(GITHUB, BATCH, 8, "merge_group")


@pytest.mark.parametrize("queue", ["mergify", "github", None])
def test_push_skips_a_commit_whose_tree_a_batch_run_tested(queue):
    api = forge("t1", batches=[queue_run(queue or "mergify")])
    found = nightly.tested_by_batch(api, "o/r", "ci.yml", MAIN, queue)
    assert found and found["html_url"].startswith("https://example.test/runs/")


@pytest.mark.parametrize("queue", ["mergify", "github", None])
def test_push_runs_when_no_batch_tested_the_tree(queue):
    api = forge("t2", batches=[queue_run(queue or "github")])
    assert nightly.tested_by_batch(api, "o/r", "ci.yml", MAIN, queue) is None


def test_the_queue_picks_the_batch_prefix_and_event():
    """A GitHub batch is a merge_group run on gh-readonly-queue/, a Mergify one a pull_request run on
    mergify/merge-queue/: under one queue the other's batch tested nothing."""
    other = {"mergify": "github", "github": "mergify"}
    for queue, wrong in other.items():
        api = forge("t1", batches=[queue_run(wrong)])
        assert nightly.tested_by_batch(api, "o/r", "ci.yml", MAIN, queue) is None
    # GitHub's batch listed as a pull_request run (the old filter), or Mergify's prefix on a github repo: ignored
    odd = [run(GITHUB, BATCH, 9, "pull_request")]
    assert (
        nightly.tested_by_batch(forge("t1", batches=odd), "o/r", "ci.yml", MAIN, "github") is None
    )


def test_push_ignores_runs_that_are_not_a_merge_queue_batch():
    pr = [run("feature", BATCH, 8)]
    assert (
        nightly.tested_by_batch(forge("t1", batches=pr), "o/r", "ci.yml", MAIN, "mergify") is None
    )


def test_nightly_skips_when_main_is_the_last_green_commit():
    api = Forge(
        {"/repos/o/r/actions/workflows/ci.yml/runs": runs(run("main", MAIN, 5, "schedule"))}
    )
    found = nightly.last_green_is(api, "o/r", "ci.yml", "main", MAIN)
    assert found and found["html_url"] == "https://example.test/runs/5"


def test_nightly_runs_when_main_moved_or_has_no_green():
    moved = Forge(
        {"/repos/o/r/actions/workflows/ci.yml/runs": runs(run("main", OTHER, 5, "schedule"))}
    )
    assert nightly.last_green_is(moved, "o/r", "ci.yml", "main", MAIN) is None
    none = Forge({"/repos/o/r/actions/workflows/ci.yml/runs": runs()})
    assert nightly.last_green_is(none, "o/r", "ci.yml", "main", MAIN) is None


def verb(monkeypatch, tmp_path, mode: str, api, queue=None, note="land.queue is test"):
    """`nightly.py moved <mode>` with a fake forge and policy; returns (exit code, GITHUB_OUTPUT, step summary)."""
    out, summary = tmp_path / "out", tmp_path / "summary"
    for name, value in {
        "GITHUB_OUTPUT": out,
        "GITHUB_STEP_SUMMARY": summary,
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_SHA": MAIN,
        "GITHUB_WORKFLOW_REF": "o/r/.github/workflows/ci.yml@refs/heads/main",
    }.items():
        monkeypatch.setenv(name, str(value))
    monkeypatch.setattr(nightly, "land_queue", lambda: (queue, note))
    code = nightly.moved(argparse.Namespace(mode=mode), api)
    return code, out.read_text() if out.exists() else "", summary.read_text()


def failing(path: str):
    raise urllib.error.URLError("boom")


@pytest.mark.parametrize("queue", ["mergify", "github"])
def test_verb_push_writes_skip_and_names_the_batch_run(monkeypatch, tmp_path, queue):
    code, out, summary = verb(
        monkeypatch, tmp_path, "push", forge("t1", batches=[queue_run(queue)]), queue
    )
    assert code == 0 and out.strip() == "skip=true"
    assert "https://example.test/runs/" in summary and "land.queue is test" in summary


@pytest.mark.parametrize("queue", ["mergify", "github"])
def test_verb_push_runs_when_nothing_tested_the_tree_or_the_forge_fails(
    monkeypatch, tmp_path, queue
):
    code, out, _ = verb(
        monkeypatch, tmp_path, "push", forge("t2", batches=[queue_run(queue)]), queue
    )
    assert code == 0 and out.strip() == "skip=false"
    (tmp_path / "out").unlink()
    code, out, summary = verb(monkeypatch, tmp_path, "push", failing, queue)
    assert code == 0 and out.strip() == "skip=false" and summary.startswith("Running")


def test_verb_schedule_skips_runs_and_runs_on_a_forge_failure(monkeypatch, tmp_path):
    green = Forge(
        {"/repos/o/r/actions/workflows/ci.yml/runs": runs(run("main", MAIN, 5, "schedule"))}
    )
    code, out, summary = verb(monkeypatch, tmp_path, "schedule", green)
    assert code == 0 and out.strip() == "skip=true" and "runs/5" in summary
    moved = Forge(
        {"/repos/o/r/actions/workflows/ci.yml/runs": runs(run("main", OTHER, 5, "schedule"))}
    )
    (tmp_path / "out").unlink()
    assert verb(monkeypatch, tmp_path, "schedule", moved)[1].strip() == "skip=false"
    (tmp_path / "out").unlink()
    assert verb(monkeypatch, tmp_path, "schedule", failing)[1].strip() == "skip=false"


def test_land_queue_reads_the_policy_of_the_checkout(tmp_path, monkeypatch):
    """Through the gatekeeper's reader: `mergify` and `github` pick one queue, an unset one reads both and says so."""
    monkeypatch.setenv("GATEKEEPER_POLICY_FROM_WORKING_TREE", "1")
    monkeypatch.chdir(tmp_path)
    import subprocess

    subprocess.run(["git", "init", "-q"], check=True)
    agents = tmp_path / "docs" / "agents"
    agents.mkdir(parents=True)
    for text, expected in (
        ("land:\n  queue: github\n", "github"),
        ("land:\n  queue: mergify\n", "mergify"),
        ("loop:\n  owner: x\n", None),
    ):
        (agents / "gatekeeper.md").write_text(f"# Policy\n\n## Policy\n\n```yaml\n{text}```\n")
        queue, note = nightly.land_queue()
        assert queue == expected, note
        assert note.startswith(f"land.queue is {expected or 'unset'}")
    (agents / "gatekeeper.md").write_text("no block here\n")
    queue, note = nightly.land_queue()
    assert queue is None and "unreadable" in note and "both queues" in note


def steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["qualify"]["steps"]


def test_workflow_reads_the_forge_and_skips_with_step_level_ifs_only():
    doc = yaml.safe_load(WORKFLOW.read_text())
    assert doc["permissions"]["actions"] == "read"
    assert "if" not in doc["jobs"]["qualify"], (
        "`qualify` is a required check: it must report on every PR"
    )
    lookup = [s for s in steps() if s.get("id") == "tested"]
    assert len(lookup) == 1 and "scripts/nightly.py moved" in lookup[0]["run"]
    guarded = [s for s in steps() if "steps.tested.outputs.skip" in str(s.get("if", ""))]
    commands = [s.get("run", "").strip() for s in guarded]
    assert "mise run check-fast" in commands and "mise run check" in commands
    assert {"mise install", "uv sync --frozen"} <= set(commands), "a skipped run installs nothing"
    assert any("mise-action" in s.get("uses", "") for s in guarded)
    assert any("cache/save" in s.get("uses", "") for s in guarded), (
        "the test-map save is skipped with the run"
    )


def test_skill_text_points_to_the_rule_and_names_the_forge_read():
    lead = (SKILL / "lead.md").read_text()
    step9 = lead[lead.index("9. **Accept.**") :][:900]
    assert "tested" in step9 and f"SKILL.md, {HEADING}" in step9
    skill = (SKILL / "SKILL.md").read_text()
    nightly = skill[skill.index("**Nightly.**") :][:1800]
    assert "last green" in nightly and "moved since" in nightly and HEADING in nightly


def test_push_asks_only_for_successful_runs_and_reads_the_next_page():
    asked: list[str] = []
    full = [run("feature", OTHER, n) for n in range(100)]
    base = forge("t1")

    def api(path: str):
        asked.append(path)
        if "/runs?" in path:
            return runs(*full) if path.endswith("&page=1") else runs(run(MERGIFY, BATCH, 7))
        return base(path)

    assert nightly.tested_by_batch(api, "o/r", "ci.yml", MAIN, "mergify")["id"] == 7
    assert all("status=success" in p for p in asked if "/runs?" in p)


@pytest.mark.parametrize("kind", ["mergify", "github"])
def test_an_unset_queue_reads_the_batches_of_both(kind):
    api = forge("t1", batches=[queue_run(kind)])
    assert nightly.tested_by_batch(api, "o/r", "ci.yml", MAIN, None)


def test_the_nightly_asks_only_for_successful_scheduled_runs_on_the_branch():
    asked: list[str] = []

    def api(path: str):
        asked.append(path)
        return runs()

    nightly.last_green_is(api, "o/r", "ci.yml", "main", MAIN)
    assert (
        "event=schedule" in asked[0] and "status=success" in asked[0] and "branch=main" in asked[0]
    )
