"""scripts/approvals.py: each loop step leaves proof on GitHub; the gate checks it, and `approve`/`verdict` write it."""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts"
SPEC = importlib.util.spec_from_file_location("approvals", SCRIPTS / "approvals.py")
assert SPEC and SPEC.loader
approvals = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(approvals)

PROJECT = Path(__file__).resolve().parent / "fixtures" / "loop-project"
TRACKER = (PROJECT / "docs" / "agents" / "issue-tracker.md").read_text()
LOOP = (PROJECT / "docs" / "agents" / "loop.md").read_text()
HEAD = "a" * 40
WRITTEN = "2026-10-01T09:00:00Z"
AS_WRITTEN = "as written 2026-10-01 09:00:00 UTC"
IDS = itertools.count(1)
PUSHED, LABELED = "2026-10-01T10:00:00Z", "2026-10-01T11:00:00Z"


@pytest.fixture(autouse=True)
def pushed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The head was pushed at PUSHED, before the PR's labels were added (LABELED); a test says otherwise."""
    monkeypatch.setattr(approvals, "head_pushed", lambda _pull: PUSHED)


def problems(issues: list[dict[str, Any]]) -> list[str]:
    return approvals.problems(issues, approvals.label_names(TRACKER))


def note(body: str, **fields: Any) -> dict[str, Any]:
    """A comment as GitHub returns it, written by the account running approvals.py unless a test says otherwise."""
    return {
        "id": f"IC_{next(IDS)}",
        "body": body,
        "createdAt": WRITTEN,
        "lastEditedAt": None,
        "isMinimized": False,
        "viewerCanMinimize": True,
        **fields,
    }


def node(
    labels: tuple[str, ...] = (), comments: tuple[str | dict[str, Any], ...] = (), **fields: Any
) -> dict[str, Any]:
    return {
        "labels": {"nodes": [{"name": name} for name in labels]},
        "comments": {
            "nodes": [body if isinstance(body, dict) else note(body) for body in comments]
        },
        **fields,
    }


def issue(
    number: int, *labels: str, body: str = "the spec", comments: tuple[str, ...] = ()
) -> dict[str, Any]:
    return node(labels, comments, number=number, body=body, createdAt=WRITTEN, lastEditedAt=None)


def specced(number: int, *labels: str) -> dict[str, Any]:
    return issue(number, "web", "size:S", *labels)


def record(point: str, by: str, **fields: str) -> str:
    return "\n".join(
        [
            f"Approved: {point}",
            f"By: {by}",
            *(f"{key.capitalize()}: {value}" for key, value in fields.items()),
        ]
    )


def approved(
    number: int, *labels: str, owner: bool = False, body: str = "the spec"
) -> dict[str, Any]:
    """A specced issue whose spec the coordinator, and the owner when asked, approved."""
    comments = (record("spec", "coordinator", spec=AS_WRITTEN),) + (
        (record("spec", "owner", spec=AS_WRITTEN),) if owner else ()
    )
    return issue(number, "size:S", "approved:spec", *labels, body=body, comments=comments)


def pull(
    *,
    body: str = "## Evidence\n\nlog line\n",
    files: tuple[str, ...] = (),
    comments: tuple[str, ...] = (),
    labels: tuple[str, ...] = (),
    checks: tuple[tuple[str, str], ...] = (("check", "SUCCESS"),),
    labeled: str = LABELED,
) -> dict[str, Any]:
    contexts = [
        {"__typename": "CheckRun", "name": name, "status": "COMPLETED", "conclusion": state}
        for name, state in checks
    ]
    return node(
        labels,
        comments,
        number=7,
        body=body,
        baseRefName="main",
        headRefName="feature",
        headRefOid=HEAD,
        baseRepository={"nameWithOwner": "kzarzycki/scratch-gate-revert"},
        files={"nodes": [{"path": path} for path in files]},
        commits={"nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": contexts}}}}]},
        closingIssuesReferences={"nodes": []},
        timelineItems={
            "nodes": [{"createdAt": labeled, "label": {"name": name}} for name in labels]
        },
    )


VERDICT = f"Verifier verdict\nHead: {HEAD}\nVERDICT: 0 blocker, 1 major, 0 minor\nSATISFIED: yes\n"
OWNED = ("approved:merge",)


def merge(pr: dict[str, Any], issues: list[dict[str, Any]], loop: str = LOOP) -> list[str]:
    """check merge's lines: what fails, then what it waits for."""
    return approvals.proofs("merge", pr, issues, loop) + approvals.waits(pr, loop)


# --- labels and state ---


def test_the_label_rule_is_the_loops_fixed_set_plus_the_tracker_files_sections() -> None:
    assert approvals.label_names(TRACKER) == {
        "category": {"bug", "enhancement", "documentation", "chore", "ops"},
        "component": {"agents", "api", "web"},
        "size": {"size:XS", "size:S", "size:M", "size:L", "size:XL"},
    }
    assert approvals.listed(TRACKER, "Sizes") == set()  # no such section


def test_a_pr_that_closes_no_issue_skipped_the_spec() -> None:
    assert problems([]) == [
        "the PR names no issue: it needs a `Closes #<spec>` or `Part of #<spec>` line for an approved spec"
    ]


def test_a_parked_issue_is_named() -> None:
    found = problems(
        [
            specced(1, "bug"),
            issue(3, "needs-owner", "bug", "api", "size:M"),
            specced(4, "bug", "needs-owner"),
        ]
    )
    assert found == [
        "#3 waits for the owner (needs-owner)",
        "#4 waits for the owner (needs-owner)",
    ]


def test_an_approved_spec_with_a_size_is_ready_without_ready_for_agent() -> None:
    ready = approved(1, "bug", "web")
    assert problems([ready]) + approvals.proofs("build", pull(), [ready], LOOP) == []


def test_an_issue_without_approved_spec_is_not_ready() -> None:
    intent = issue(2, "chore", "agents", "size:XS", "ready-for-agent")
    assert problems([intent]) + approvals.proofs("build", pull(), [intent], LOOP) == [
        "#2 has no `Approved: spec` record by the coordinator",
        "#2 lacks the `approved:spec` label",
    ]


def test_every_closing_issue_specced_lands() -> None:
    assert problems([specced(1, "ops", "triaged-by-bot"), specced(2, "bug", "api")]) == []


def test_a_specced_issue_without_exactly_one_category_is_named() -> None:
    found = problems([specced(1), specced(2, "bug", "chore")])
    categories = "bug, chore, documentation, enhancement, ops"
    assert found == [
        f"#1 needs exactly one category label ({categories}), has 0",
        f"#2 needs exactly one category label ({categories}), has 2",
    ]


def test_a_wayfinder_ticket_needs_only_its_state() -> None:
    assert problems([issue(58, "wayfinder:task", "approved:spec")]) == []
    assert problems([issue(58, "wayfinder:task", "ready-for-agent")]) == [
        "#58 lacks `approved:spec`: spec it first"
    ]
    merged = pull(comments=(VERDICT,), labels=OWNED)
    assert merge(merged, [issue(58, "wayfinder:task")]) == []


def test_a_specced_issue_without_a_component_or_exactly_one_size_is_named() -> None:
    found = problems([issue(1, "bug"), specced(2, "bug", "size:M")])
    sizes = "size:L, size:M, size:S, size:XL, size:XS"
    assert found == [
        f"#1 needs exactly one size label ({sizes}), has 0",
        "#1 needs a component label (agents, api, web)",
        f"#2 needs exactly one size label ({sizes}), has 2",
    ]


def test_a_tracker_file_without_components_says_so() -> None:
    assert (
        approvals.problems([specced(1, "bug")], approvals.label_names(""))[-1]
        == "#1 needs a component label (docs/agents/issue-tracker.md lists none)"
    )


@pytest.mark.parametrize(
    ("body", "numbers"),
    [
        ("Closes #549", [549]),
        ("Closes #556.\n\n## Summary", [556]),
        ("fixes #1, Resolved: #2 and CLOSE #3; closes #1\tclosed #4", [1, 2, 3, 4]),
        ("An example: `Closes #5`, <!-- Closes #6 -->\n```\nFixes #7\n```\nCloses #8", [8]),
        ("## Fixes\n\n#12 and closes\n#13; closes #14x", []),
        (
            "- step:\n  ```\n  Fixes #7\n  ```\n> ```\n> Fixes #9\n> ```\n```\nx ``` y\nFixes #10\n```\nCloses #8",
            [8],
        ),
        ("Use ``` inline.\nCloses #15\n```\ncode\n```\nRun `a` then\nFixes:\t#16\n`b`", [15, 16]),
        ("Fix #7\nfixed #8\nresolve #9\nresolves #10", [7, 8, 9, 10]),
        ("Part of #11\npart of: #12; departs of #13, part #14", [11, 12]),
        ("", []),
        ("See #12; follows #13. Discloses #14, prefix #15, closes owner/repo#16, closes#17", []),
    ],
)
def test_the_body_names_its_closing_issues(body: str, numbers: list[int]) -> None:
    assert approvals.named(body) == numbers


# --- approval rules ---


def test_loop_md_rules_and_practice_are_read_from_their_sections() -> None:
    assert approvals.rules(LOOP) == [
        ("spec", "size:L or larger, or component `api`"),
    ]
    assert not approvals.practice_plans(LOOP)
    assert approvals.practice_plans("## Practice\n\n- Plan: writing-plans\n")


@pytest.mark.parametrize(
    ("condition", "labels", "paths", "hit"),
    [
        ("always", set(), [], True),
        ("size:L or larger", {"size:XL"}, [], True),
        ("size:L+", {"size:M"}, [], False),
        ("size:L", {"size:XL"}, [], False),
        ("size:L or larger, or component `api`", {"size:S", "api"}, [], True),
        ("category ops", {"bug"}, [], False),
        ("path `billing/**`", set(), ["billing/a/invoice.py"], True),
        ("path `billing/**`", set(), ["web/app.ts"], False),
        ("path `billing/**`", set(), None, None),
        ("size:L+ or path `billing/**`", {"size:XL"}, None, True),
        ("a change that can place live orders", {"size:XL"}, [], None),
        ("size:L or a schema change", {"size:L"}, [], None),
    ],
)
def test_a_condition_holds_or_is_left_to_the_loop(
    condition: str, labels: set[str], paths: list[str] | None, hit: bool | None
) -> None:
    assert approvals.matches(condition, labels, paths) is hit


# --- proof at build ---


def test_an_approved_spec_passes_build() -> None:
    assert approvals.proofs("build", pull(), [approved(1, "web")], LOOP) == []


def test_a_spec_nobody_approved_is_named() -> None:
    assert approvals.proofs("build", pull(), [specced(1, "bug")], LOOP) == [
        "#1 has no `Approved: spec` record by the coordinator",
        "#1 lacks the `approved:spec` label",
    ]


def test_a_spec_is_named_by_its_last_edit_as_github_shows_it() -> None:
    assert approvals.version({"createdAt": WRITTEN, "lastEditedAt": None}) == AS_WRITTEN
    edited = {"createdAt": WRITTEN, "lastEditedAt": "2026-10-02T14:35:27Z"}
    assert approvals.version(edited) == "as edited 2026-10-02 14:35:27 UTC"


def test_a_spec_edited_after_its_approval_needs_approving_again() -> None:
    edited = approved(1, "web")
    edited["lastEditedAt"] = "2026-10-02T14:35:27Z"
    assert approvals.proofs("build", pull(), [edited], LOOP) == [
        "#1 has no `Approved: spec` record by the coordinator for its current spec: approve again"
    ]


def test_a_matching_rule_needs_the_owner_too() -> None:
    assert approvals.proofs("build", pull(), [approved(1, "api")], LOOP) == [
        "#1 has no `Approved: spec` record by the owner"
    ]
    assert approvals.proofs("build", pull(), [approved(1, "api", owner=True)], LOOP) == []


def test_a_spec_in_a_comment_is_the_one_approved() -> None:
    spec = "## Spec\n\nthe real spec"
    labels = ("ready-for-agent", "size:S", "web", "approved:spec")
    edited = "2026-10-02T11:00:00Z"
    comments = (
        note(spec, lastEditedAt=edited),
        record("spec", "coordinator", spec="as edited 2026-10-02 11:00:00 UTC"),
    )
    tool_owned = issue(1, *labels, body="a tool's body", comments=comments)
    assert approvals.proofs("build", pull(), [tool_owned], LOOP) == []


def test_a_heading_is_the_comments_whole_first_line() -> None:
    notes = (
        "## Spec\n\nthe old spec",
        "## Specification notes\n\nnot a spec",
        "  ## Spec  \nthe spec",
    )
    found = approvals.headed(issue(1, comments=notes), "## Spec")
    assert found is not None and found["body"] == "  ## Spec  \nthe spec"
    assert approvals.headed(issue(1, comments=notes[1:2]), "## Spec") is None
    assert approvals.headed(issue(1, comments=("## Plan\n1. a",)), "## Plan") is not None


def test_a_due_plan_needs_its_comment_and_approval() -> None:
    plans = "## Practice\n\n- Plan: writing-plans\n"
    assert approvals.proofs("build", pull(), [approved(1, "web")], plans) == [
        "#1 has no `## Plan` comment, and one is due"
    ]
    assert (
        approvals.proofs("build", pull(), [approved(1, "web")], "## Approvals\n\n- plan: always\n")
        == []
    )
    planned = approved(1, "web")
    planned["comments"]["nodes"].append(note("## Plan\n\n1. slice"))
    assert approvals.proofs("build", pull(), [planned], "") == [
        "#1 has no `Approved: plan` record by the coordinator",
        "#1 lacks the `approved:plan` label",
    ]


# --- proof at merge ---


def test_a_pr_with_every_proof_passes_merge() -> None:
    checks = (("check", "SUCCESS"), ("pr-board / sync", "FAILURE"))
    done = pull(comments=(VERDICT,), labels=OWNED, checks=checks)
    assert merge(done, [approved(1, "web")]) == []


def test_a_merge_waits_for_check_and_the_owners_label_and_fails_a_missing_proof(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def gated(pr: dict[str, Any]) -> tuple[int, list[str]]:
        pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
        monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
        code = approvals.main(["check", "merge", "7"])
        return code, capsys.readouterr().out.splitlines()

    monkeypatch.chdir(PROJECT)
    running = pull(comments=(VERDICT,), checks=(("check", "IN_PROGRESS"),))
    assert gated(running) == (
        approvals.WAITING,
        [
            "PR #7: `check` is IN_PROGRESS on the head commit",
            "PR #7 waits for the owner's `approved:merge` label",
        ],
    )
    assert gated(pull(comments=(VERDICT,), labels=OWNED)) == (0, [])
    assert gated(pull(labels=OWNED, checks=(("check", "IN_PROGRESS"),))) == (
        1,
        [
            "PR #7: no verifier verdict posted (approvals.py verdict)",
            "PR #7: `check` is IN_PROGRESS on the head commit",
        ],
    )


def test_a_label_added_before_the_heads_push_is_no_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = pull(comments=(VERDICT,), labels=OWNED, labeled="2026-10-01T09:59:59Z")
    assert merge(stale, [approved(1, "web")]) == [
        "PR #7: `approved:merge` was added before the head was pushed: the owner adds it again"
    ]
    monkeypatch.setattr(approvals, "head_pushed", lambda _pull: None)
    assert merge(pull(comments=(VERDICT,), labels=OWNED), [approved(1, "web")]) == [
        f"PR #7: GitHub lists no push of the head {HEAD}, so `approved:merge` can't be dated after it"
    ]


def test_the_head_was_pushed_when_the_branchs_activity_last_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.undo()  # the autouse fixture's stub of head_pushed
    monkeypatch.setattr(approvals, "gh", lambda *args: calls.append(args) or f"{PUSHED}\n")
    assert approvals.head_pushed(pull()) == PUSHED
    assert calls == [
        (
            "api",
            "repos/{owner}/{repo}/activity?ref=refs/heads/feature&per_page=100",
            "--jq",
            f'[.[] | select(.after == "{HEAD}") | .timestamp] | first // ""',
        )
    ]
    monkeypatch.setattr(approvals, "gh", lambda *args: "\n")
    assert approvals.head_pushed(pull()) is None


def run(name: str, conclusion: str, started: str, workflow: str = "CI") -> dict[str, Any]:
    """A check run as the rollup returns it, with its start and its workflow."""
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": "COMPLETED",
        "conclusion": conclusion,
        "startedAt": started,
        "checkSuite": {"workflowRun": {"workflow": {"name": workflow}}},
    }


def with_runs(*runs: dict[str, Any]) -> dict[str, Any]:
    pr = pull()
    pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"] = list(runs)
    return pr


def test_only_the_aggregate_check_is_read() -> None:
    pr = with_runs(
        run("lint", "FAILURE", "2026-10-03T13:00:00Z"),
        {"__typename": "StatusContext", "context": "loop:approvals", "state": "PENDING"},
    )
    assert approvals.ci("PR #7", pr) == ["PR #7: no `check` on the head commit yet"]
    pr = with_runs(run("lint", "FAILURE", "2026-10-03T13:00:00Z"), run("check", "SUCCESS", ""))
    assert approvals.ci("PR #7", pr) == []


def test_a_run_cancelled_by_a_newer_green_run_of_the_same_check_is_not_a_problem() -> None:
    pr = with_runs(
        run("check", "CANCELLED", "2026-10-03T13:44:42Z"),
        run("check", "SUCCESS", "2026-10-03T13:44:49Z"),
    )
    assert approvals.ci("PR #7", pr) == []


def test_the_newest_run_of_a_check_counts_when_it_failed() -> None:
    pr = with_runs(
        run("check", "SUCCESS", "2026-10-03T13:00:00Z"),
        run("check", "FAILURE", "2026-10-03T14:00:00Z"),
    )
    assert approvals.ci("PR #7", pr) == ["PR #7: `check` is FAILURE on the head commit"]


def test_one_job_name_in_two_workflows_is_two_checks() -> None:
    pr = with_runs(
        run("check", "SUCCESS", "2026-10-03T14:00:00Z", "CI"),
        run("check", "FAILURE", "2026-10-03T13:00:00Z", "Nightly"),
    )
    assert approvals.ci("PR #7", pr) == ["PR #7: `check` is FAILURE on the head commit"]


def test_without_ci_the_merge_proof_is_a_local_check_recorded_on_the_head() -> None:
    no_ci = LOOP + "\nCI: none\n"
    missing = [
        (
            "PR #7: the project has no CI (loop.md `CI: none`), and no local check passed on"
            " the head (approvals.py local-ci)"
        )
    ]

    def proofs(*comments: str) -> list[str]:
        merged = pull(comments=(VERDICT, *comments), labels=OWNED, checks=())
        return merge(merged, [approved(1, "web")], no_ci)

    assert (
        proofs(),
        proofs(f"{approvals.CHECKED}\nHead: {'b' * 40}\nCommand: mise run check\n"),
        proofs("## Evidence\n\n- `mise run check`: exit 0\n"),
        proofs(f"{approvals.CHECKED}: no, not run\nHead: {HEAD}\n"),
        proofs(f"> {approvals.CHECKED}\n> Head: {HEAD}\n"),
        proofs(f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check\n"),
    ) == (missing, missing, missing, missing, missing, [])


@pytest.mark.parametrize(
    ("line", "opted_out"),
    [
        ("CI: none", True),
        ("- CI: none", True),
        ("* `CI: none`", True),
        ("CI: none (Actions is off for billing)", True),
        ("CI: none of the checks may fail", False),
        ("The CI: none here", False),
    ],
)
def test_only_a_bare_ci_none_line_opts_out_of_ci(line: str, opted_out: bool) -> None:
    assert (
        re.search(approvals.NO_CI, f"## Gates\n\n{line}\n", re.MULTILINE) is not None
    ) == opted_out


def test_more_checks_than_one_page_is_refused() -> None:
    big = pull(comments=(VERDICT,), labels=OWNED, checks=(("lint", "SUCCESS"),))
    big["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["totalCount"] = 101
    assert merge(big, [approved(1, "web")]) == [
        "PR #7 has more than 1 CI checks: the gate reads one page",
    ]


def test_more_comments_than_one_page_is_refused(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    crowded = pull(comments=(VERDICT, "a note"), labels=OWNED)
    crowded["comments"]["totalCount"] = 101
    crowded["closingIssuesReferences"]["nodes"] = [approved(1, "web")]
    monkeypatch.setattr(approvals, "pull_request", lambda _n: crowded)
    monkeypatch.chdir(PROJECT)
    assert (approvals.main(["check", "merge", "7"]), capsys.readouterr().out) == (
        1,
        "#7 has more than 2 comments: the gate reads one page\n",
    )


def test_a_path_rule_on_the_spec_is_left_to_the_loop() -> None:
    rule = "## Approvals\n\n- spec: path `billing/**`\n"
    assert (
        approvals.proofs("build", pull(files=("billing/a.py",)), [approved(1, "web")], rule) == []
    )


def test_a_pr_without_its_proof_names_each_missing_one() -> None:
    bare = pull(body="## Evidence\n\n## Summary\n", checks=(("check", "FAILURE"),))
    assert merge(bare, [approved(1, "web")]) == [
        "PR #7: its body has no `## Evidence` section with content",
        "PR #7: no verifier verdict posted (approvals.py verdict)",
        "PR #7: `check` is FAILURE on the head commit",
        "PR #7 waits for the owner's `approved:merge` label",
    ]
    assert "PR #7: no `check` on the head commit yet" in merge(pull(checks=()), [], "")


def test_a_merge_rule_in_loop_md_changes_nothing_the_owner_approves_every_merge() -> None:
    billing = pull(files=("billing/invoice.py",), comments=(VERDICT,), labels=OWNED)
    assert merge(billing, [approved(1, "web")]) == []


# --- an exact revert ---

# GitHub's REST answers from a scratch round trip, trimmed to what the gate reads where noted: #1 merged (pull-1.json
# trimmed), #2 the PR GitHub's Revert button made for it after main moved, #3 that revert plus one line, still open;
# #2's merge base (trimmed) and the trees (trimmed to path, mode and type) of #1's base and merge commit and of #2's
# merge base and head.
REVERTED = Path(__file__).resolve().parent / "fixtures" / "reverts"
REVERT_BASE, REVERT_HEAD = (
    "340b9aa38acac5a0d84e8c6d276a6ed2f3afdbe4",
    "47e28a794ff0884f8631342b8ed1aae4733e1ba6",
)
REVERT_BODY = "Reverts kzarzycki/scratch-gate-revert#1\n\n## Evidence\n\n#1 set the wrong rate.\n"


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """gh answering REST calls from the recordings, a 404 for any other number; the paths asked for."""
    asked: list[str] = []

    def gh(*args: str, data: str | None = None) -> str:
        path = next(arg for arg in args if arg.startswith("repos/"))
        asked.append(path)
        name = re.sub(r"^repos/\{owner\}/\{repo\}/pulls/(\d+)(/files)?.*", r"pull-\1\2", path)
        name = re.sub(r"^repos/\{owner\}/\{repo\}/git/trees/(\w+)\?recursive=1$", r"tree-\1", name)
        name = re.sub(r"^repos/\{owner\}/\{repo\}/(compare)/", r"\1-", name)
        found = REVERTED / f"{name.replace('/', '-')}.json"
        if not found.exists():
            raise subprocess.CalledProcessError(1, "gh", stderr="gh: Not Found (HTTP 404)\n")
        if "/files" in path:  # as `--jq '.[]'` prints them
            assert args[-2:] == ("--jq", ".[]")
            return "".join(json.dumps(entry) + "\n" for entry in json.loads(found.read_text()))
        if "/compare/" in path:  # as `--jq .merge_base_commit.sha` prints it
            assert args[-2:] == ("--jq", ".merge_base_commit.sha")
            return json.loads(found.read_text())["merge_base_commit"]["sha"] + "\n"
        return found.read_text()

    monkeypatch.setattr(approvals, "gh", gh)
    monkeypatch.chdir(PROJECT)
    return asked


def revert_pr(number: int = 2, body: str = REVERT_BODY, **fields: Any) -> dict[str, Any]:
    """The revert PR as GitHub's GraphQL returns it: the paths it touches are #1's."""
    return {
        **pull(body=body, files=("app.py", "billing/rate.py", "notes.py"), **fields),
        "number": number,
        "baseRefOid": REVERT_BASE,
        "headRefOid": REVERT_HEAD,
    }


def gated(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    point: str,
    pr: dict[str, Any],
) -> tuple[int, list[str]]:
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    code = approvals.main(["check", point, str(pr["number"])])
    return code, capsys.readouterr().out.splitlines()


def test_an_exact_revert_lands_without_a_spec_or_a_verdict(
    recorded: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    done = revert_pr(labels=OWNED)
    assert gated(monkeypatch, capsys, "build", done) == (0, [])
    assert gated(monkeypatch, capsys, "merge", done) == (0, [])
    # the inverse comes from GitHub's own diff of #1, not from anything approvals.py writes
    assert "repos/{owner}/{repo}/pulls/1/files?per_page=100" in recorded
    # the modes come from the trees of #1's base and merge commit and of the revert's merge base and head
    assert {
        "repos/{owner}/{repo}/git/trees/2a90fbed44fbe633bd17dff0af93d5ea1b5d3fe6?recursive=1",
        "repos/{owner}/{repo}/git/trees/6417e28b25ef79e8a0e6406bad2e2ae03a8330c3?recursive=1",
        f"repos/{{owner}}/{{repo}}/compare/{REVERT_BASE}...{REVERT_HEAD}",
        f"repos/{{owner}}/{{repo}}/git/trees/{REVERT_BASE}?recursive=1",
        f"repos/{{owner}}/{{repo}}/git/trees/{REVERT_HEAD}?recursive=1",
    } <= set(recorded)


def test_an_exact_revert_still_needs_check_and_the_merge_approval(
    recorded: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    red = revert_pr(labels=OWNED, checks=(("check", "FAILURE"),))
    assert gated(monkeypatch, capsys, "merge", red) == (
        approvals.WAITING,
        ["PR #2: `check` is FAILURE on the head commit"],
    )
    unapproved = revert_pr(body="Reverts #1\n\n## Evidence\n\n#1 set the wrong rate.\n")
    assert gated(monkeypatch, capsys, "merge", unapproved) == (
        approvals.WAITING,
        ["PR #2 waits for the owner's `approved:merge` label"],
    )
    bare = revert_pr(body="Reverts #1\n", labels=OWNED)
    assert gated(monkeypatch, capsys, "merge", bare) == (
        1,
        ["PR #2: its body has no `## Evidence` section with content"],
    )


def test_a_revert_with_one_extra_line_gets_every_proof_of_any_pr(
    recorded: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plus = revert_pr(3, labels=OWNED)
    assert gated(monkeypatch, capsys, "merge", plus) == (
        1,
        [
            (
                "PR #3 is not an exact revert of #1: `billing/rate.py` has 1 line(s) beyond the"
                " inverse of #1, 0 missing. It needs every proof of any PR"
            ),
            (
                "the PR names no issue: it needs a `Closes #<spec>` or `Part of #<spec>` line for an"
                " approved spec"
            ),
            "PR #3: no verifier verdict posted (approvals.py verdict)",
        ],
    )


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("Reverts #3", "#3 is not a merged pull request"),
        ("Reverts #9", "#9 is not a merged pull request"),
        (
            "Reverts other/fork#1",
            "it names a PR of other/fork, and this is kzarzycki/scratch-gate-revert",
        ),
    ],
)
def test_reverts_naming_no_merged_pr_here_is_refused(
    recorded: list[str], line: str, why: str
) -> None:
    number = re.findall(r"\d+", line)[-1]
    assert approvals.reverts(revert_pr(body=f"{line}\n")) == (
        None,
        [f"PR #2 is not an exact revert of #{number}: {why}. It needs every proof of any PR"],
    )


def test_a_quoted_or_mid_line_reverts_is_no_revert(recorded: list[str]) -> None:
    for body in ("`Reverts #1`\n", "This Reverts #1\n", "```\nReverts #1\n```\n"):
        assert approvals.reverts(revert_pr(body=body)) == (None, [])
    assert recorded == []


def entry(filename: str, patch: str | None, **fields: Any) -> dict[str, Any]:
    return {
        "filename": filename,
        "status": "modified",
        "changes": 1,
        **({"patch": patch} if patch else {}),
        **fields,
    }


def test_the_inverse_ignores_line_numbers_and_context_and_follows_renames() -> None:
    original = [
        entry("a.py", "@@ -1,3 +1,3 @@\n one\n-two\n+2\n three"),
        entry("new.py", "@@ -1,2 +1,2 @@\n-x\n+y", previous_filename="old.py", status="renamed"),
    ]
    revert = [
        entry("a.py", "@@ -10,2 +10,2 @@\n moved context\n-2\n+two"),
        entry("old.py", "@@ -1 +1 @@\n-y\n+x", previous_filename="new.py", status="renamed"),
    ]
    assert approvals.inexact(original, revert, 1, NONE, NONE) == []
    moved = revert[:1] + [entry("new.py", "@@ -1 +1 @@\n-y\n+x")]
    assert approvals.inexact(original, moved, 1, NONE, NONE) == [
        "it changes `new.py`, which #1 did not",
        "it leaves `old.py -> new.py` as #1 changed it",
    ]


def test_a_file_github_shows_no_diff_of_is_no_exact_revert() -> None:
    assert approvals.inexact(
        [entry("logo.png", None)], [entry("logo.png", None)], 1, NONE, NONE
    ) == [
        "GitHub shows no diff of `logo.png` to compare",
        "GitHub shows no diff of `logo.png` to compare",
    ]
    unchanged = {"filename": "run.sh", "status": "modified", "changes": 0, "patch": ""}
    assert approvals.inexact([unchanged], [unchanged], 1, NONE, NONE) == [
        "GitHub shows no diff of `run.sh` to compare",
        "GitHub shows no diff of `run.sh` to compare",
    ]


def test_a_missing_final_newline_counts() -> None:
    assert approvals.changed_lines("@@ -1 +1 @@\n-x\n\\ No newline at end of file\n+x") == [
        (["x"], ["x\n\\ no newline"])
    ]


CALLS = "@@ -1,2 +1,2 @@\n-authorize()\n-transfer()\n+authorize_v2()\n+transfer_v2()"
UNDO_CALLS = "@@ -3,2 +3,2 @@\n-authorize_v2()\n-transfer_v2()\n+authorize()\n+transfer()"
MODES = {"app.py": "100644"}
# the trees before and after a PR: none of the paths, and app.py's mode kept
NONE: tuple[dict[str, str], dict[str, str]] = ({}, {})
KEPT = (MODES, MODES)


def test_the_inverse_keeps_the_order_of_changed_lines() -> None:
    original = [entry("app.py", CALLS)]
    assert approvals.inexact(original, [entry("app.py", UNDO_CALLS)], 1, KEPT, KEPT) == []
    swapped = UNDO_CALLS.replace("+authorize()\n+transfer()", "+transfer()\n+authorize()")
    assert approvals.inexact(original, [entry("app.py", swapped)], 1, KEPT, KEPT) == [
        "`app.py` changes the lines #1 changed in another order"
    ]
    # the same lines in the same order, one of them moved into another run
    two = [entry("app.py", "@@ -1,3 +1,3 @@\n-a\n+b\n x\n-c\n+d")]
    moved = [entry("app.py", "@@ -1,3 +1,3 @@\n-b\n+a\n+c\n x\n-d")]
    assert approvals.inexact(two, moved, 1, KEPT, KEPT) == [
        "`app.py` changes the lines #1 changed in another order"
    ]


def test_a_revert_that_changes_a_mode_is_no_exact_revert() -> None:
    exact = ([entry("app.py", CALLS)], [entry("app.py", UNDO_CALLS)], 1)
    assert approvals.inexact(*exact, KEPT, (MODES, {"app.py": "100755"})) == [
        "`app.py` has mode 100755 at the head, and 100644 before #1"
    ]
    for truncated in ((None, MODES), (MODES, None)):
        assert approvals.inexact(*exact, truncated, KEPT) == [
            "GitHub truncates a tree it would compare file modes in"
        ]
        assert approvals.inexact(*exact, KEPT, truncated) == [
            "GitHub truncates a tree it would compare file modes in"
        ]


def test_a_revert_that_also_undoes_a_later_mode_change_is_no_exact_revert() -> None:
    """#1 kept app.py's mode, main made it executable after, and the revert branches from there and resets it: its
    head has app.py's mode from before #1, but it undoes main's change too."""
    exact = ([entry("app.py", CALLS)], [entry("app.py", UNDO_CALLS)], 1)
    assert approvals.inexact(*exact, KEPT, ({"app.py": "100755"}, MODES)) == [
        "`app.py` has mode 100755 at the merge base, and 100644 after #1"
    ]


def test_an_empty_file_left_in_place_is_no_exact_revert() -> None:
    added = {"filename": "run.sh", "status": "added", "changes": 0}
    moded = {"filename": "run.sh", "status": "modified", "changes": 0}
    assert approvals.inexact(
        [added],
        [moded],
        1,
        ({}, {"run.sh": "100644"}),
        ({"run.sh": "100644"}, {"run.sh": "100755"}),
    ) == [
        "GitHub shows no diff of `run.sh` to compare",
        "GitHub shows no diff of `run.sh` to compare",
        "`run.sh` is modified, and undoing #1 needs removed",
        "`run.sh` has mode 100755 at the head, and absent before #1",
    ]


# --- writing proof ---


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Every write approvals.py makes, instead of making it."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        approvals, "comment", lambda number, body: calls.append(("comment", number, body))
    )
    monkeypatch.setattr(
        approvals, "label", lambda number, name, add: calls.append(("label", number, name, add))
    )
    monkeypatch.setattr(
        approvals, "minimize", lambda comment_id: calls.append(("minimize", comment_id))
    )
    monkeypatch.chdir(PROJECT)
    return calls


def test_the_coordinator_approves_a_spec_no_rule_holds(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "issue_node", lambda _n: specced(1, "bug"))
    assert approvals.main(["approve", "spec", "1", "--by", "coordinator"]) == 0
    assert github == [
        ("comment", 1, f"Approved: spec\nBy: coordinator\nSpec: {AS_WRITTEN}\n"),
        ("label", 1, "approved:spec", True),
    ]


def test_a_rule_leaves_the_label_to_the_owner(
    github: list[tuple[Any, ...]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        approvals, "issue_node", lambda _n: specced(1, "bug", "size:XL", "approved:spec")
    )
    assert approvals.main(["approve", "spec", "1", "--by", "coordinator"]) == 0
    assert github[1:] == [("label", 1, "approved:spec", False), ("label", 1, "needs-owner", True)]
    assert "stop until they add `approved:spec`" in capsys.readouterr().out
    github.clear()
    assert approvals.main(["approve", "spec", "1", "--by", "owner"]) == 0
    assert github[1:] == [("label", 1, "approved:spec", True), ("label", 1, "needs-owner", False)]


def test_a_re_approval_says_why_and_minimizes_what_it_supersedes(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = note(record("spec", "coordinator", spec=AS_WRITTEN))
    owners = note(record("spec", "owner", spec=AS_WRITTEN))
    edited = specced(1, "bug", "size:XL")
    edited["comments"]["nodes"] = [stale, owners]
    edited["lastEditedAt"] = "2026-10-02T14:35:27Z"
    monkeypatch.setattr(approvals, "issue_node", lambda _n: edited)
    assert approvals.main(["approve", "spec", "1", "--by", "coordinator"]) == 0
    assert github[:3] == [
        (
            "comment",
            1,
            (
                "Approved: spec\nBy: coordinator\nSpec: as edited 2026-10-02 14:35:27 UTC\n"
                "The spec changed after the last approval, so it was checked again.\n"
            ),
        ),
        ("minimize", stale["id"]),
        ("minimize", owners["id"]),
    ]


def test_another_approvers_record_of_the_same_version_stays_open(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinators = note(record("spec", "coordinator", spec=AS_WRITTEN))
    repeated = note(record("spec", "owner", spec=AS_WRITTEN))
    done = specced(1, "bug", "size:XL")
    done["comments"]["nodes"] = [coordinators, repeated]
    monkeypatch.setattr(approvals, "issue_node", lambda _n: done)
    assert approvals.main(["approve", "spec", "1", "--by", "owner"]) == 0
    assert github[:2] == [
        ("comment", 1, f"Approved: spec\nBy: owner\nSpec: {AS_WRITTEN}\n"),
        ("minimize", repeated["id"]),
    ]
    assert ("minimize", coordinators["id"]) not in github


def test_a_comment_gate_py_cannot_or_need_not_minimize_is_left_alone(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    theirs = note(
        record("spec", "coordinator", spec="as written 2026-09-01 09:00:00 UTC"),
        viewerCanMinimize=False,
    )
    hidden = note(
        record("spec", "coordinator", spec="as written 2026-09-02 09:00:00 UTC"), isMinimized=True
    )
    old = specced(1, "bug")
    old["comments"]["nodes"] = [theirs, hidden]
    monkeypatch.setattr(approvals, "issue_node", lambda _n: old)
    assert approvals.main(["approve", "spec", "1", "--by", "coordinator"]) == 0
    assert [call for call in github if call[0] == "minimize"] == []


def test_merge_is_no_approve_point(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        approvals.main(["approve", "merge", "7", "--by", "coordinator"])
    assert exited.value.code == 2
    assert "invalid choice: 'merge'" in capsys.readouterr().err


def test_the_verdict_posts_the_reports_last_lines(
    github: list[tuple[Any, ...]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pull())
    report = tmp_path / "report.md"
    report.write_text("findings\nVERDICT: 0 blocker, 1 major, 0 minor\nSATISFIED: yes\n")
    assert approvals.main(["verdict", "7", str(report)]) == 0
    assert github == [("comment", 7, VERDICT)]
    report.write_text("findings, unfinished\n")
    assert approvals.main(["verdict", "7", str(report)]) == 1
    assert (
        capsys.readouterr().out == f"{report} has no `SATISFIED:` line: the report is unfinished\n"
    )


# --- check end to end, GitHub stubbed ---


def test_check_without_a_pr_has_nothing_to_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(approvals, "current_pr", lambda: None)
    monkeypatch.chdir(PROJECT)
    assert (approvals.main(["check", "build"]), capsys.readouterr().out) == (
        0,
        "no PR for this branch yet: nothing to gate\n",
    )


def test_a_closing_line_with_no_such_issue_fails_with_the_reason(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refused(_pr: int) -> dict[str, Any]:
        raise subprocess.CalledProcessError(
            1,
            "gh",
            stderr="gh: Could not resolve to an issue or pull request with the number of 9.\n",
        )

    monkeypatch.setattr(approvals, "pull_request", refused)
    monkeypatch.chdir(PROJECT)
    assert (approvals.main(["check", "build", "1"]), capsys.readouterr().out) == (
        1,
        "gh: Could not resolve to an issue or pull request with the number of 9.\n",
    )


def test_run_outside_a_repo_with_a_tracker_file_fails_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert (approvals.main(["check", "build", "1"]), capsys.readouterr().out) == (
        1,
        "docs/agents/issue-tracker.md: No such file or directory: run from the repo root\n",
    )


def test_check_reads_the_projects_own_components_and_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    agents = tmp_path / "docs" / "agents"
    agents.mkdir(parents=True)
    (agents / "issue-tracker.md").write_text(
        "## Components\n\n- `billing`: invoices.\n\n## Extra categories\n\n- `research`\n"
    )
    (agents / "loop.md").write_text("## Approvals\n\nNone.\n")
    pr = pull()
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "billing", "research")]
    monkeypatch.setattr(approvals, "pull_request", lambda _pr: pr)
    monkeypatch.chdir(tmp_path)
    assert (approvals.main(["check", "build", "7"]), capsys.readouterr().out) == (0, "")


# --- local-ci: the local check, run on the PR head ---


@pytest.fixture
def checkout(github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A checkout at the PR head and clean; a test changes it, or what the check does to it."""
    state: dict[str, Any] = {"head": HEAD, "status": "", "exit": 0, "after": None}

    def git(*args: str) -> str:
        if args[0] == "rev-parse":
            return state["head"] + "\n"
        if args[0] == "ls-files":
            return "H app.py\n"
        assert args == (
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        return state["status"]

    def run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        assert (command, check) == (["mise", "run", "check:all"], False)
        if state["after"]:
            state["status"] = state["after"]
        return subprocess.CompletedProcess(command, state["exit"])

    monkeypatch.setattr(approvals, "pull_request", lambda _n: pull())
    monkeypatch.setattr(approvals, "git", git)
    monkeypatch.setattr(approvals.subprocess, "run", run)
    return state


def test_a_passing_check_on_the_clean_head_is_recorded(
    github: list[tuple[Any, ...]], checkout: dict[str, Any]
) -> None:
    assert approvals.main(["local-ci", "7"]) == 0
    assert github == [
        ("comment", 7, f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check:all\n")
    ]


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"head": "b" * 40}, f"the checkout is at {'b' * 40}, PR #7's head is {HEAD}"),
        ({"status": " M app.py\n"}, "the tree has changes"),
        ({"exit": 2}, "mise run check:all exited 2: nothing recorded"),
        ({"after": " M uv.lock\n"}, "mise run check:all changed the checkout"),
    ],
)
def test_a_check_off_the_head_failed_or_changing_the_tree_records_nothing(
    github: list[tuple[Any, ...]],
    checkout: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    change: dict[str, Any],
    said: str,
) -> None:
    checkout.update(change)
    assert approvals.main(["local-ci", "7"]) == 1
    assert github == []
    assert said in capsys.readouterr().out


def test_a_local_ci_record_is_the_merge_proof_without_ci(
    github: list[tuple[Any, ...]], checkout: dict[str, Any]
) -> None:
    assert approvals.main(["local-ci", "7"]) == 0
    posted = [body for kind, _pr, body in github if kind == "comment"]
    merged = pull(comments=(VERDICT, *posted), labels=OWNED, checks=())
    assert merge(merged, [approved(1, "web")], LOOP + "\nCI: none\n") == []


@pytest.mark.parametrize("change", [{}, {"exit": 2}])
def test_record_check_is_local_ci(
    github: list[tuple[Any, ...]],
    checkout: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    change: dict[str, Any],
) -> None:
    checkout.update(change)
    runs = []
    for name in ("local-ci", "record-check"):
        github.clear()
        runs.append((approvals.main([name, "7"]), capsys.readouterr().out, list(github)))
    assert runs[0] == runs[1]


@pytest.mark.parametrize(
    "args",
    [["check", "build", "7"], ["verdict", "7", "report.md"], ["check", "deploy"], ["--help"]],
)
def test_gate_py_is_approvals_py(tmp_path: Path, args: list[str]) -> None:
    def ran(script: str) -> tuple[int, str, str]:
        done = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return done.returncode, done.stdout, done.stderr

    assert ran("gate.py") == ran("approvals.py")


def git_in(where: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "-C", str(where), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def committed(where: Path) -> str:
    where.mkdir(exist_ok=True)
    git_in(where, "init", "-q")
    git_in(where, "config", "user.email", "loop@example.com")
    git_in(where, "config", "user.name", "loop")
    (where / "app.py").write_text("value = 1\n")
    git_in(where, "add", "-A")
    git_in(where, "commit", "-qm", "base")
    return git_in(where, "rev-parse", "HEAD").strip()


def hidden_untracked(repo: Path) -> None:
    git_in(repo, "config", "status.showUntrackedFiles", "no")
    (repo / "new.py").write_text("")


def hidden_submodule_edit(repo: Path) -> None:
    committed(repo.parent / "lib")
    git_in(repo, "submodule", "add", "-q", str(repo.parent / "lib"), "lib")
    git_in(repo, "commit", "-qm", "lib")
    git_in(repo, "config", "submodule.lib.ignore", "all")
    (repo / "lib" / "app.py").write_text("value = 2\n")


def hidden_by_ignore_stat(repo: Path) -> None:
    git_in(repo, "config", "core.ignoreStat", "true")
    (repo / "lib.py").write_text("value = 1\n")
    git_in(repo, "add", "lib.py")  # core.ignoreStat marks it assume-unchanged
    git_in(repo, "commit", "-qm", "lib")
    (repo / "lib.py").write_text("value = 2\n")


@pytest.mark.parametrize("hide", [hidden_untracked, hidden_submodule_edit, hidden_by_ignore_stat])
def test_a_change_the_status_config_hides_still_records_nothing(
    github: list[tuple[Any, ...]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hide: Any,
) -> None:
    repo = tmp_path / "repo"
    committed(repo)
    hide(repo)
    head = git_in(repo, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(approvals, "pull_request", lambda _n: {**pull(), "headRefOid": head})
    monkeypatch.chdir(repo)
    assert approvals.main(["local-ci", "7"]) == 1
    assert github == []
    assert "the tree has changes" in capsys.readouterr().out
