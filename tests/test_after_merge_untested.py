"""R7, after the merge only a tree nobody tested runs (#2179): tools/tested_tree.py decides, from the forge, whether
the push run on main or the nightly has anything to run, `engineering-ci.yml` wires it in, and the skill text points
to the rule instead of restating it."""

from __future__ import annotations

from pathlib import Path

import yaml

from tools import tested_tree

REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "loop" / "skills" / "engineering-loop"
WORKFLOW = REPOSITORY / ".github" / "workflows" / "engineering-ci.yml"
HEADING = "A check runs only if it can fail because of the change"

MAIN = "a" * 40
BATCH = "b" * 40
OTHER = "c" * 40


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
    batches = [run("mergify/merge-queue/x", BATCH, 7)] if batches is None else batches
    return Forge(
        {
            "/repos/o/r/actions/workflows/ci.yml/runs": runs(*batches),
            f"/repos/o/r/git/commits/{BATCH}": {"tree": {"sha": batch_tree}},
            f"/repos/o/r/git/commits/{MAIN}": {"tree": {"sha": main_tree}},
            f"/repos/o/r/git/commits/{OTHER}": {"tree": {"sha": "t9"}},
        }
    )


def test_push_skips_a_commit_whose_tree_a_batch_run_tested():
    found = tested_tree.tested_by_batch(forge("t1"), "o/r", "ci.yml", MAIN)
    assert found and found["html_url"] == "https://example.test/runs/7"


def test_push_runs_when_no_batch_tested_the_tree():
    assert tested_tree.tested_by_batch(forge("t2"), "o/r", "ci.yml", MAIN) is None


def test_push_ignores_runs_that_are_not_a_merge_queue_batch():
    pr = [run("feature", BATCH, 8)]
    assert tested_tree.tested_by_batch(forge("t1", batches=pr), "o/r", "ci.yml", MAIN) is None


def test_nightly_skips_when_main_is_the_last_green_commit():
    api = Forge(
        {"/repos/o/r/actions/workflows/ci.yml/runs": runs(run("main", MAIN, 5, "schedule"))}
    )
    found = tested_tree.last_green_is(api, "o/r", "ci.yml", "main", MAIN)
    assert found and found["html_url"] == "https://example.test/runs/5"


def test_nightly_runs_when_main_moved_or_has_no_green():
    moved = Forge(
        {"/repos/o/r/actions/workflows/ci.yml/runs": runs(run("main", OTHER, 5, "schedule"))}
    )
    assert tested_tree.last_green_is(moved, "o/r", "ci.yml", "main", MAIN) is None
    none = Forge({"/repos/o/r/actions/workflows/ci.yml/runs": runs()})
    assert tested_tree.last_green_is(none, "o/r", "ci.yml", "main", MAIN) is None


def test_main_writes_the_output_and_the_summary_naming_the_run(tmp_path, monkeypatch):
    out, summary = tmp_path / "out", tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    code = tested_tree.report(
        "push", tested_tree.tested_by_batch(forge("t1"), "o/r", "ci.yml", MAIN)
    )
    assert code == 0
    assert "skip=true" in out.read_text()
    assert "https://example.test/runs/7" in summary.read_text()
    out.write_text("")
    tested_tree.report("push", None)
    assert out.read_text().strip() == "skip=false"


def steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["qualify"]["steps"]


def test_workflow_reads_the_forge_and_skips_with_step_level_ifs_only():
    doc = yaml.safe_load(WORKFLOW.read_text())
    assert doc["permissions"]["actions"] == "read"
    assert "if" not in doc["jobs"]["qualify"], (
        "`qualify` is a required check: it must report on every PR"
    )
    lookup = [s for s in steps() if s.get("id") == "tested"]
    assert len(lookup) == 1 and "tools/tested_tree.py" in lookup[0]["run"]
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
            return (
                runs(*full)
                if path.endswith("&page=1")
                else runs(run("mergify/merge-queue/x", BATCH, 7))
            )
        return base(path)

    assert tested_tree.tested_by_batch(api, "o/r", "ci.yml", MAIN)["id"] == 7
    assert all("status=success" in p for p in asked if "/runs?" in p)


TAG_WORKFLOW = REPOSITORY / ".github" / "workflows" / "engineering-tag-check.yml"


def test_tag_skips_when_a_green_nightly_ran_the_tagged_commit():
    """#2264: the tag check's `test` and `test-slow` are the nightly's, so a green nightly on the tagged commit
    already passed them; an older nightly counts too, since the commit, not main's head, is what was tagged."""
    asked: list[str] = []

    def api(path: str):
        asked.append(path)
        return runs(run("main", MAIN, 5, "schedule"))

    found = tested_tree.nightly_ran(api, "o/r", "engineering-ci.yml", MAIN)
    assert found and found["html_url"] == "https://example.test/runs/5"
    query = f"?event=schedule&status=success&head_sha={MAIN}&per_page=1"
    assert asked == ["/repos/o/r/actions/workflows/engineering-ci.yml/runs" + query]


def test_tag_runs_when_no_green_nightly_ran_the_tagged_commit():
    none = Forge({"/repos/o/r/actions/workflows/engineering-ci.yml/runs": runs()})
    assert tested_tree.nightly_ran(none, "o/r", "engineering-ci.yml", MAIN) is None
    # a forge that ignored the head_sha filter returns another commit's run, which proves nothing
    other = Forge(
        {
            "/repos/o/r/actions/workflows/engineering-ci.yml/runs": runs(
                run("main", OTHER, 5, "schedule")
            )
        }
    )
    assert tested_tree.nightly_ran(other, "o/r", "engineering-ci.yml", MAIN) is None


def test_tag_mode_reads_the_nightly_and_a_forge_failure_runs_the_suite(tmp_path, monkeypatch):
    """In the tag check GITHUB_WORKFLOW_REF names the tag workflow, so `tag` must ask for the nightly's runs by
    name; a forge it can't read writes skip=false."""
    out = tmp_path / "out"
    for name, value in {
        "GITHUB_OUTPUT": str(out),
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_SHA": MAIN,
        "GITHUB_WORKFLOW_REF": "o/r/.github/workflows/engineering-tag-check.yml@refs/tags/engineering-v1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    asked: list[str] = []

    def api(path: str):
        asked.append(path)
        return runs(run("main", MAIN, 5, "schedule"))

    monkeypatch.setattr(tested_tree, "github", api)
    assert tested_tree.main(["tag"]) == 0
    assert out.read_text().strip() == "skip=true"
    assert all("/workflows/engineering-ci.yml/" in path for path in asked)

    def down(path: str):
        raise OSError("forge down")

    monkeypatch.setattr(tested_tree, "github", down)
    out.write_text("")
    assert tested_tree.main(["tag"]) == 0
    assert out.read_text().strip() == "skip=false"


def test_tag_workflow_skips_only_the_nightlys_suites():
    """The release check, the vendor check and the package gate run on every tag, since the nightly runs none of
    them; `test` and `test-slow` skip on `skip=true`; the forge read gets `actions: read` in `qualify` alone."""
    doc = yaml.safe_load(TAG_WORKFLOW.read_text())
    qualify = doc["jobs"]["qualify"]
    assert qualify["permissions"] == {"contents": "read", "actions": "read"}
    assert doc["permissions"] == {"contents": "read"}, "consumer-sync keeps its permissions"
    assert "if" not in qualify
    order = [s.get("id") or s.get("run", "").strip() for s in qualify["steps"] if "run" in s]
    assert order.index("tested") < order.index("mise install")
    lookup = next(s for s in qualify["steps"] if s.get("id") == "tested")
    assert lookup["run"] == "python3 tools/tested_tree.py tag"
    assert lookup["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
    guarded = {
        s["run"].strip()
        for s in qualify["steps"]
        if s.get("if") == "steps.tested.outputs.skip != 'true'"
    }
    assert guarded == {"mise run test", "mise run test-slow"}
