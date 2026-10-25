"""scripts/approvals.py: each loop step leaves proof on GitHub; the gate checks it, and `approve`/`verdict` write it."""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import subprocess
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
HEAD, BASE = "a" * 40, "b" * 40
WRITTEN = "2026-10-01T09:00:00Z"
AS_WRITTEN = "as written 2026-10-01 09:00:00 UTC"
IDS = itertools.count(1)
PUSHED, LABELED = "2026-10-01T10:00:00Z", "2026-10-01T11:00:00Z"
# land's wait for a check whose only run is the draft's skip
WAITED = (
    "PR #7: no `check` on the head commit yet since the PR went ready"
    " (its workflow may lack the `ready_for_review` type)"
)
TOPLEVEL = approvals.toplevel
VIEWER = approvals.viewer


@pytest.fixture(autouse=True)
def pushed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The head was pushed at PUSHED, before the PR's labels were added (LABELED), and the directory a test runs in
    is the checkout's root; a test says otherwise."""
    monkeypatch.setattr(approvals, "head_pushed", lambda _pull: PUSHED)
    monkeypatch.setattr(approvals, "toplevel", Path.cwd)
    monkeypatch.setattr(approvals, "viewer", lambda: "loop")


@pytest.fixture(autouse=True)
def added(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str, bool]]:
    """Every label approvals.py adds or removes, instead of making the call; `github` records them with the rest."""
    calls: list[tuple[int, str, bool]] = []
    monkeypatch.setattr(
        approvals, "label", lambda number, name, add: calls.append((number, name, add))
    )
    return calls


@pytest.fixture(autouse=True)
def assigned(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Every assignee approvals.py adds or removes, and the record claim() comments, instead of making the call."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        approvals, "assign", lambda number, login, add: calls.append((number, login, add))
    )
    real = approvals.comment

    def comment(number: int, body: str) -> None:
        if body.startswith(approvals.ASSIGNED):
            calls.append((number, body))
        else:
            real(number, body)

    monkeypatch.setattr(approvals, "comment", comment)
    return calls


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
    return issue(number, "area:web", "size:S", *labels)


def record(point: str, by: str, **fields: str) -> str:
    return "\n".join(
        [
            f"Approved: {point}",
            f"By: {by}",
            *(f"{key.capitalize()}: {value}" for key, value in fields.items()),
        ]
    )


def approved(number: int, *labels: str, body: str = "the spec") -> dict[str, Any]:
    """A specced issue whose spec the owner approved."""
    comments = (record("spec", "owner", spec=AS_WRITTEN),)
    return issue(number, "size:S", "approved:spec", *labels, body=body, comments=comments)


def pull(
    *,
    body: str = "## Evidence\n\nlog line\n",
    files: tuple[str, ...] = (),
    comments: tuple[str, ...] = (),
    labels: tuple[str, ...] = (),
    checks: tuple[tuple[str, str], ...] = (("check", "SUCCESS"),),
    labeled: str = LABELED,
    reviews: tuple[dict[str, Any], ...] = (),
    latest: tuple[str, ...] = (),
    threads: tuple[bool, ...] = (),
) -> dict[str, Any]:
    contexts = [
        {"__typename": "CheckRun", "name": name, "status": "COMPLETED", "conclusion": state}
        for name, state in checks
    ]
    return node(
        labels,
        comments,
        number=7,
        title="Feature",
        isCrossRepository=False,
        author={"login": "worker"},
        state="OPEN",
        isDraft=False,
        mergeStateStatus="BLOCKED",
        autoMergeRequest=None,
        isInMergeQueue=False,
        body=body,
        baseRefName="main",
        baseRefOid=BASE,
        headRefName="feature",
        headRefOid=HEAD,
        baseRepository={"nameWithOwner": "kzarzycki/scratch-gate-revert"},
        files={"nodes": [{"path": path} for path in files]},
        latestReviews={
            "nodes": [{"state": state, "author": {"login": "reviewer"}} for state in latest]
        },
        reviews={"nodes": list(reviews)},
        reviewThreads={"nodes": [{"isResolved": resolved} for resolved in threads]},
        commits={"nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": contexts}}}}]},
        closingIssuesReferences={"nodes": []},
        timelineItems={
            "nodes": [{"createdAt": labeled, "label": {"name": name}} for name in labels]
        },
    )


def verdict_on(
    commit: str,
    counts: str = "0 blocker, 0 major, 1 minor",
    satisfied: str = "yes",
    author: str | None = "loop",
    heading: str = "Verifier (claude), pass 1",
) -> dict[str, Any]:
    """A verifier pass's PR review as GitHub's GraphQL returns it, by the account running approvals.py."""
    return {
        "author": {"login": author} if author else None,
        "state": "COMMENTED",
        "commit": {"oid": commit},
        "body": f"{heading} on {commit[:7]}.\n\nVERDICT: {counts}\nSATISFIED: {satisfied}\n",
    }


VERDICT = verdict_on(HEAD, "0 blocker, 0 major, 2 minor")
OWNED = ("approved:merge",)
HELD = "PR #7 waits for the owner's `approved:merge` label, since it is high risk: "
BILLING = HELD + "it matches a risk rule (path `billing/**`)"
GITHUB = HELD + "it matches a risk rule (path `.github/**`)"


def merge(pr: dict[str, Any], issues: list[dict[str, Any]], loop: str = LOOP) -> list[str]:
    """check merge's lines: what fails, then what it waits for."""
    return approvals.proofs("merge", pr, issues, loop) + approvals.waits(pr, issues, loop)


# --- labels and state ---


def test_the_label_rule_is_the_loops_fixed_set_plus_the_tracker_files_sections() -> None:
    assert approvals.label_names(TRACKER) == {
        "category": {
            "kind:bug",
            "kind:enhancement",
            "kind:chore",
            "kind:documentation",
            "kind:ops",
        },
        "component": {"area:agents", "area:api", "area:web"},
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
            specced(1, "kind:bug"),
            issue(3, "needs-owner", "kind:bug", "area:api", "size:M"),
            specced(4, "kind:bug", "needs-owner"),
        ]
    )
    assert found == [
        "#3 waits for the owner (needs-owner)",
        "#4 waits for the owner (needs-owner)",
    ]


def test_an_approved_spec_with_a_size_is_ready_without_ready_for_agent() -> None:
    ready = approved(1, "kind:bug", "area:web")
    assert problems([ready]) + approvals.proofs("build", pull(), [ready], LOOP) == []


def test_an_issue_without_approved_spec_is_not_ready() -> None:
    intent = issue(2, "kind:chore", "area:agents", "size:XS", "ready-for-agent")
    assert problems([intent]) + approvals.proofs("build", pull(), [intent], LOOP) == [
        "#2 has no `Approved: spec` record by the owner",
        "#2 lacks the `approved:spec` label",
    ]


def test_every_closing_issue_specced_lands() -> None:
    assert (
        problems([specced(1, "kind:ops", "triaged-by-bot"), specced(2, "kind:bug", "area:api")])
        == []
    )


def test_a_specced_issue_without_exactly_one_category_is_named() -> None:
    found = problems([specced(1), specced(2, "kind:bug", "kind:chore")])
    categories = "kind:bug, kind:chore, kind:documentation, kind:enhancement, kind:ops"
    assert found == [
        f"#1 needs exactly one category label ({categories}), has 0",
        f"#2 needs exactly one category label ({categories}), has 2",
    ]


def test_a_wayfinder_ticket_needs_only_its_state() -> None:
    assert problems([issue(58, "wayfinder:task", "approved:spec")]) == []
    assert problems([issue(58, "wayfinder:task", "ready-for-agent")]) == [
        "#58 lacks `approved:spec`: spec it first"
    ]
    merged = pull(reviews=(VERDICT,), labels=OWNED)
    assert merge(merged, [issue(58, "wayfinder:task")]) == []


def test_a_specced_issue_without_a_component_or_exactly_one_size_is_named() -> None:
    found = problems([issue(1, "kind:bug"), specced(2, "kind:bug", "size:M")])
    sizes = "size:L, size:M, size:S, size:XL, size:XS"
    assert found == [
        f"#1 needs exactly one size label ({sizes}), has 0",
        "#1 needs a component label (area:agents, area:api, area:web)",
        f"#2 needs exactly one size label ({sizes}), has 2",
    ]


def test_a_tracker_file_without_components_says_so() -> None:
    assert (
        approvals.problems([specced(1, "kind:bug")], approvals.label_names(""))[-1]
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
        ("Implements #20\nimplements: #21; reimplements #22, implement #23", [20, 21]),
        ("", []),
        ("See #12; follows #13. Discloses #14, prefix #15, closes owner/repo#16, closes#17", []),
    ],
)
def test_the_body_names_its_closing_issues(body: str, numbers: list[int]) -> None:
    assert approvals.named(body) == numbers


def test_each_link_keeps_its_kind_and_a_closing_keyword_wins() -> None:
    body = (
        "Implements #1\nPart of #2\nCloses #3\nPart of #4, implements #4\nImplements #5\nfixes #5"
    )
    assert approvals.links(body) == {
        1: approvals.IMPLEMENTS,
        2: approvals.PART,
        3: approvals.CLOSES,
        4: approvals.IMPLEMENTS,
        5: approvals.CLOSES,
    }


# --- approval rules ---


def test_loop_md_rules_and_practice_are_read_from_their_sections() -> None:
    assert approvals.rules(LOOP) == [
        ("spec", "auto unless risk"),
        ("merge", "auto unless risk"),
        ("risk", "size:L or larger, or component `api`"),
        ("risk", "path `billing/**`"),
        ("merge", "path `.github/**`"),
    ]
    assert approvals.policy(LOOP, "spec") and approvals.policy(LOOP, "merge")
    assert not approvals.policy("## Approvals\n\n- spec: always\n", "spec")
    # the policy lines are no conditions; a legacy `merge:` or `spec:` condition is a risk rule
    assert approvals.risk_rules(LOOP) == [
        "size:L or larger, or component `api`",
        "path `billing/**`",
        "path `.github/**`",
    ]
    assert not approvals.practice_plans(LOOP)
    assert approvals.practice_plans("## Practice\n\n- Plan: writing-plans\n")
    # without the spec policy the owner approves every spec, so a legacy `spec:` line holds no merge
    legacy = "## Approvals\n\n- spec: always\n- merge: path `.github/**`\n"
    assert approvals.risk_rules(legacy) == ["path `.github/**`"]


@pytest.mark.parametrize(
    ("condition", "labels", "paths", "hit"),
    [
        ("always", set(), [], True),
        ("size:L or larger", {"size:XL"}, [], True),
        ("size:L+", {"size:M"}, [], False),
        ("size:L", {"size:XL"}, [], False),
        ("size:L or larger, or component `api`", {"size:S", "area:api"}, [], True),
        ("size:L or larger, or component `api`", {"api"}, [], False),
        ("component area:api", {"area:api"}, [], True),
        ("category ops", {"kind:bug"}, [], False),
        ("category bug", {"kind:bug"}, [], True),
        ("path `billing/**`", set(), ["billing/a/invoice.py"], True),
        ("path `billing/**`", set(), ["web/app.ts"], False),
        ("path `billing/**`", set(), None, None),
        ("size:L+ or path `billing/**`", {"size:XL"}, None, True),
        ("path .github/**", set(), [".github/ci.yml"], True),
        ("path .github/**", set(), ["README.md"], False),
        ("path: .github/**, or component `api`", {"area:api"}, ["README.md"], True),
        ("path docs/*.md or size:L", set(), ["docs/a.md"], True),
        ("path .github/** for the CI", set(), [".github/ci.yml"], None),
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
    assert approvals.proofs("build", pull(), [approved(1, "area:web")], LOOP) == []


def test_a_spec_nobody_approved_is_named() -> None:
    assert approvals.proofs("build", pull(), [specced(1, "kind:bug")], "") == [
        "#1 has no `Approved: spec` record by the owner",
        "#1 lacks the `approved:spec` label",
    ]


def test_a_spec_is_named_by_its_last_edit_as_github_shows_it() -> None:
    assert approvals.version({"createdAt": WRITTEN, "lastEditedAt": None}) == AS_WRITTEN
    edited = {"createdAt": WRITTEN, "lastEditedAt": "2026-10-02T14:35:27Z"}
    assert approvals.version(edited) == "as edited 2026-10-02 14:35:27 UTC"


def test_a_spec_edited_after_its_approval_needs_approving_again() -> None:
    edited = approved(1, "area:web")
    edited["lastEditedAt"] = "2026-10-02T14:35:27Z"
    assert approvals.proofs("build", pull(), [edited], LOOP) == [
        "#1 has no `Approved: spec` record by the owner for its current spec: the owner approves it again"
    ]


def test_only_the_owners_record_approves_a_spec_and_no_coordinators_is_asked_for() -> None:
    """`check` and `land` read the owner's record alone: an agent's record approves nothing."""
    agents = issue(
        1, "size:S", "approved:spec", comments=(record("spec", "coordinator", spec=AS_WRITTEN),)
    )
    assert approvals.proofs("build", pull(), [agents], "") == [
        "#1 has no `Approved: spec` record by the owner"
    ]
    assert approvals.proofs("build", pull(), [approved(1, "area:api")], "") == []


def test_a_spec_in_a_comment_is_the_one_approved() -> None:
    spec = "## Spec\n\nthe real spec"
    labels = ("ready-for-agent", "size:S", "area:web", "approved:spec")
    edited = "2026-10-02T11:00:00Z"
    comments = (
        note(spec, lastEditedAt=edited),
        record("spec", "owner", spec="as edited 2026-10-02 11:00:00 UTC"),
    )
    tool_owned = issue(1, *labels, body="a tool's body", comments=comments)
    assert approvals.proofs("build", pull(), [tool_owned], LOOP) == []


def test_a_leading_ai_marker_line_is_skipped_when_reading_a_heading() -> None:
    notes = [
        "> 🤖 AI\n\n## Spec\n\nthe marked spec",
        "> 🤖 AI\n\n## Specification notes\n\nnot a spec",
    ]
    found = approvals.headed(issue(1, comments=notes), "## Spec")
    assert found is not None and found["body"].endswith("the marked spec")
    assert approvals.headed(issue(1, comments=notes[1:]), "## Spec") is None


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
    assert approvals.proofs("build", pull(), [approved(1, "area:web")], plans) == [
        "#1 has no `## Plan` comment, and one is due"
    ]
    assert (
        approvals.proofs(
            "build", pull(), [approved(1, "area:web")], "## Approvals\n\n- plan: always\n"
        )
        == []
    )
    planned = approved(1, "area:web")
    planned["comments"]["nodes"].append(note("## Plan\n\n1. slice"))
    assert approvals.proofs("build", pull(), [planned], "") == []  # no agent approves a plan either
    assert approvals.proofs("build", pull(), [planned], "## Approvals\n\n- plan: always\n") == [
        "#1 has no `Approved: plan` record by the owner",
        "#1 lacks the `approved:plan` label",
    ]


# --- proof at merge ---


def test_a_pr_with_every_proof_passes_merge() -> None:
    checks = (("check", "SUCCESS"), ("pr-board / sync", "FAILURE"))
    done = pull(reviews=(VERDICT,), labels=OWNED, checks=checks)
    assert merge(done, [approved(1, "area:web")]) == []


def test_a_merge_waits_for_check_and_the_owners_label_and_fails_a_missing_proof(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def gated(pr: dict[str, Any]) -> tuple[int, list[str]]:
        pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
        monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
        code = approvals.main(["check", "merge", "7"])
        return code, capsys.readouterr().out.splitlines()

    monkeypatch.chdir(PROJECT)
    running = pull(reviews=(VERDICT,), checks=(("check", "IN_PROGRESS"),), files=("billing/a.py",))
    assert gated(running) == (
        approvals.WAITING,
        ["PR #7: `check` is IN_PROGRESS on the head commit", BILLING],
    )
    assert gated(pull(reviews=(VERDICT,), labels=OWNED, files=("billing/a.py",))) == (0, [])
    assert gated(pull(labels=OWNED, checks=(("check", "IN_PROGRESS"),))) == (
        1,
        [
            "PR #7: no verifier review posted (approvals.py verdict)",
            "PR #7: `check` is IN_PROGRESS on the head commit",
        ],
    )


def test_a_label_added_before_the_heads_push_is_no_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    billing = ("billing/a.py",)
    stale = pull(reviews=(VERDICT,), labels=OWNED, labeled="2026-10-01T09:59:59Z", files=billing)
    assert merge(stale, [approved(1, "area:web")]) == [
        "PR #7: `approved:merge` was added before the head was pushed: the owner adds it again"
    ]
    same_second = pull(reviews=(VERDICT,), labels=OWNED, labeled=PUSHED, files=billing)
    assert merge(same_second, [approved(1, "area:web")]) == [
        "PR #7: `approved:merge` was added before the head was pushed: the owner adds it again"
    ]
    monkeypatch.setattr(approvals, "head_pushed", lambda _pull: None)
    assert merge(
        pull(reviews=(VERDICT,), labels=OWNED, files=billing), [approved(1, "area:web")]
    ) == [
        f"PR #7: GitHub lists no push of the head {HEAD}, so `approved:merge` can't be dated after it"
    ]


def test_a_label_added_again_after_the_push_is_the_approval() -> None:
    again = pull(reviews=(VERDICT,), labels=OWNED)
    again["timelineItems"]["nodes"] = [
        {"createdAt": "2026-10-01T09:00:00Z", "label": {"name": "approved:merge"}},
        {"createdAt": LABELED, "label": {"name": "approved:merge"}},
    ]
    assert merge(again, [approved(1, "area:web")]) == []


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
        merged = pull(reviews=(VERDICT,), comments=comments, labels=OWNED, checks=())
        return merge(merged, [approved(1, "area:web")], no_ci)

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
    big = pull(reviews=(VERDICT,), labels=OWNED, checks=(("lint", "SUCCESS"),))
    big["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["totalCount"] = 101
    assert merge(big, [approved(1, "area:web")]) == [
        "PR #7 has more than 1 CI checks: the gate reads one page",
    ]


def test_more_comments_than_one_page_is_refused() -> None:
    crowded = pull(comments=("a note", "another"))
    crowded["comments"]["totalCount"] = 101
    with pytest.raises(
        approvals.Refused, match="#7 has more than 2 comments: the gate reads one page"
    ):
        approvals.ran(crowded, "CI: none\n")


def test_a_path_rule_on_the_spec_is_left_to_the_loop() -> None:
    rule = "## Approvals\n\n- spec: path `billing/**`\n"
    assert (
        approvals.proofs("build", pull(files=("billing/a.py",)), [approved(1, "area:web")], rule)
        == []
    )


def test_a_pr_without_its_proof_names_each_missing_one() -> None:
    bare = pull(
        body="## Evidence\n\n## Summary\n", checks=(("check", "FAILURE"),), files=("billing/a.py",)
    )
    assert merge(bare, [approved(1, "area:web")]) == [
        "PR #7: its body has no `## Evidence` section with content",
        "PR #7: no verifier review posted (approvals.py verdict)",
        "PR #7: `check` is FAILURE on the head commit",
        BILLING,
    ]
    assert "PR #7: no `check` on the head commit yet" in merge(pull(checks=()), [], "")


def test_a_legacy_merge_rule_in_loop_md_reads_as_a_risk_rule() -> None:
    rule = "## Approvals\n\n- merge: path `billing/**`\n"
    billing = pull(files=("billing/invoice.py",), reviews=(VERDICT,))
    assert merge(billing, [approved(1, "area:web")], rule) == [BILLING]
    assert (
        merge(pull(files=("web/app.ts",), reviews=(VERDICT,)), [approved(1, "area:web")], rule)
        == []
    )
    billing["labels"]["nodes"] = [{"name": "approved:merge"}]
    billing["timelineItems"]["nodes"] = [
        {"createdAt": LABELED, "label": {"name": "approved:merge"}}
    ]
    assert merge(billing, [approved(1, "area:web")], rule) == []


# --- sign-off: the owner checks a landed change in use ---

SIGNOFF = LOOP + "- signoff: component `web` or path `app/**`\n"
LANDED = pull(reviews=(VERDICT,), labels=OWNED)


def linking(keyword: str, number: int = 1, files: tuple[str, ...] = ()) -> dict[str, Any]:
    return pull(
        body=f"{keyword} #{number}\n\n## Evidence\n\nlog line\n",
        reviews=(VERDICT,),
        labels=OWNED,
        files=files,
    )


def test_signoff_rules_are_read_from_approvals() -> None:
    assert approvals.rules(SIGNOFF)[-1] == ("signoff", "component `web` or path `app/**`")
    assert approvals.risk_rules(SIGNOFF) == approvals.risk_rules(LOOP)


def test_without_a_signoff_line_any_link_lands_as_today() -> None:
    for keyword in ("Closes", "Implements", "Part of"):
        assert merge(linking(keyword), [approved(1, "area:web")]) == []
    owner = approved(1, "area:web", body="the spec\n\nSign-off: owner\n")
    assert merge(linking("Closes"), [owner]) == []


def test_an_issue_a_signoff_rule_matches_is_implemented_not_closed() -> None:
    web = approved(1, "area:web")
    assert merge(linking("Implements"), [web], SIGNOFF) == []
    assert merge(linking("Part of"), [web], SIGNOFF) == []
    assert merge(linking("Closes"), [web], SIGNOFF) == [
        (
            "#1 waits for the owner's sign-off after landing, since it matches a sign-off rule"
            " (component `web` or path `app/**`): the PR says `Implements #1`, which leaves it open,"
            " not a closing keyword"
        )
    ]
    # GitHub's own link, with no line in the body, closes the issue on merge
    assert merge(LANDED, [web], SIGNOFF)[0].startswith("#1 waits for the owner's sign-off")
    # the PR's files and labels count, as for a risk rule
    api = approved(1, "area:api")
    assert approvals.linked(linking("Implements", files=("app/main.swift",)), [api], SIGNOFF) == []
    assert approvals.linked(linking("Implements", files=("api/a.py",)), [api], SIGNOFF) != []


def test_an_issue_no_signoff_rule_matches_is_closed() -> None:
    api = approved(1, "area:api")
    assert approvals.linked(linking("Closes"), [api], SIGNOFF) == []
    assert approvals.linked(linking("Part of"), [api], SIGNOFF) == []
    assert approvals.linked(linking("Implements"), [api], SIGNOFF) == [
        (
            "#1 needs no sign-off (no sign-off rule matches): the PR says `Closes #1`, since"
            " `Implements` would leave it open for a sign-off nobody asked for"
        )
    ]


def test_the_spec_asks_for_a_signoff_and_never_waives_a_rule() -> None:
    owner = approved(1, "area:api", body="the spec\n\n- **Sign-off:** owner\n")
    assert approvals.linked(linking("Implements"), [owner], SIGNOFF) == []
    assert approvals.linked(linking("Closes"), [owner], SIGNOFF) == [
        (
            "#1 waits for the owner's sign-off after landing, since its spec says `Sign-off: owner`:"
            " the PR says `Implements #1`, which leaves it open, not a closing keyword"
        )
    ]
    waived = approved(1, "area:web", body="the spec\n\nSign-off: none\n")
    assert approvals.linked(linking("Implements"), [waived], SIGNOFF) == []
    none = approved(1, "area:api", body="the spec\n\nSign-off: none\n")
    assert approvals.linked(linking("Implements"), [none], SIGNOFF) == [
        (
            "#1 needs no sign-off (no sign-off rule matches and its spec says `Sign-off: none`): the PR"
            " says `Closes #1`, since `Implements` would leave it open for a sign-off nobody asked for"
        )
    ]
    quoted = approved(1, "area:api", body="the spec\n\n`Sign-off: owner` is an example\n")
    assert approvals.linked(linking("Closes"), [quoted], SIGNOFF) == []


def test_a_signoff_rule_the_gate_cant_read_asks_for_the_signoff() -> None:
    vague = LOOP + "- signoff: anything a user sees\n"
    assert approvals.linked(linking("Implements"), [approved(1, "area:api")], vague) == []
    assert approvals.linked(linking("Closes"), [approved(1, "area:api")], vague)[0].startswith(
        "#1 waits for the owner's sign-off after landing, since a sign-off rule the gate can't"
        " judge holds until a person does (anything a user sees)"
    )


def test_signoff_always_asks_for_implements_and_a_rule_matching_nothing_asks_for_none() -> None:
    web = approved(1, "area:web")
    assert approvals.linked(linking("Closes"), [web], LOOP + "- signoff: always\n")[0].startswith(
        "#1 waits for the owner's sign-off after landing"
    )
    assert approvals.linked(linking("Closes"), [web], LOOP + "- signoff: component nothing\n") == []


def test_a_wayfinder_ticket_and_a_repo_without_loop_md_are_not_checked() -> None:
    ticket = issue(58, "wayfinder:task", "approved:spec", "area:web")
    assert approvals.linked(linking("Closes", 58), [ticket], SIGNOFF) == []
    assert approvals.proofs("merge", linking("Closes"), [approved(1, "area:web")], None) == []


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
        [
            "PR #2 waits for the owner's `approved:merge` label, since it is high risk: it matches a risk rule (path `billing/**`)"
        ],
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
            "PR #3: no verifier review posted (approvals.py verdict)",
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


def test_the_owners_approval_is_recorded_labelled_and_clears_needs_owner(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "issue_node", lambda _n: specced(1, "kind:bug", "needs-owner"))
    assert approvals.main(["approve", "spec", "1", "--by", "owner"]) == 0
    assert github == [
        ("comment", 1, f"Approved: spec\nBy: owner\nSpec: {AS_WRITTEN}\n"),
        ("label", 1, "approved:spec", True),
        ("label", 1, "needs-owner", False),
    ]


def test_approve_refuses_the_coordinator(
    github: list[tuple[Any, ...]], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        approvals.main(["approve", "spec", "1", "--by", "coordinator"])
    assert exited.value.code == 2
    assert "invalid choice: 'coordinator'" in capsys.readouterr().err
    assert github == []


def test_a_re_approval_says_why_and_minimizes_every_record_it_supersedes(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = note(record("spec", "coordinator", spec=AS_WRITTEN))
    owners = note(record("spec", "owner", spec=AS_WRITTEN))
    edited = specced(1, "kind:bug", "size:XL")
    edited["comments"]["nodes"] = [agents, owners]
    edited["lastEditedAt"] = "2026-10-02T14:35:27Z"
    monkeypatch.setattr(approvals, "issue_node", lambda _n: edited)
    assert approvals.main(["approve", "spec", "1", "--by", "owner"]) == 0
    assert github[:3] == [
        (
            "comment",
            1,
            (
                "Approved: spec\nBy: owner\nSpec: as edited 2026-10-02 14:35:27 UTC\n"
                "The spec changed after the last approval, so it was checked again.\n"
            ),
        ),
        ("minimize", agents["id"]),
        ("minimize", owners["id"]),
    ]


def test_a_comment_gate_py_cannot_or_need_not_minimize_is_left_alone(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    theirs = note(
        record("spec", "owner", spec="as written 2026-09-01 09:00:00 UTC"),
        viewerCanMinimize=False,
    )
    hidden = note(
        record("spec", "owner", spec="as written 2026-09-02 09:00:00 UTC"), isMinimized=True
    )
    old = specced(1, "kind:bug")
    old["comments"]["nodes"] = [theirs, hidden]
    monkeypatch.setattr(approvals, "issue_node", lambda _n: old)
    assert approvals.main(["approve", "spec", "1", "--by", "owner"]) == 0
    assert [call for call in github if call[0] == "minimize"] == []


def test_merge_is_no_approve_point(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        approvals.main(["approve", "merge", "7", "--by", "owner"])
    assert exited.value.code == 2
    assert "invalid choice: 'merge'" in capsys.readouterr().err


REPORT = f"""# Verifier report: PR #7, pass 2

Verifier: claude, same-family, pass 2

## Correctness

### C1 (blocker) app.py:12: a draft merges on its skipped checks

- Failing input: a draft.

### C2 (minor) app.py:40: a line outside the diff

Evidence: the run.

### S1 (minor) docs/old.md:3: a file outside the diff

The doc.

Head: {HEAD}
VERDICT: 1 blocker, 0 major, 2 minor
SATISFIED: no
Risk: low — a test fixture
"""


@pytest.fixture
def reviewing(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> list[tuple[Any, ...]]:
    """`verdict` against a stubbed GitHub: the PR's base, the diff's commentable lines, and each review it posts."""
    asked: list[tuple[str, str]] = []

    def diff_lines(base: str, head: str) -> dict[str, list[int]]:
        asked.append((base, head))
        return {"app.py": [10, 11, 12, 13, 30, 31]}

    monkeypatch.setattr(approvals, "pull_request", lambda _n: {**pull(), "headRefOid": "2" * 40})
    monkeypatch.setattr(approvals, "diff_lines", diff_lines)
    monkeypatch.setattr(
        approvals, "post_review", lambda pr, review: github.append(("review", pr, review))
    )
    github.append(("asked", asked))
    return github


def test_the_verdict_posts_the_report_as_a_review_on_the_commit_it_reviewed(
    reviewing: list[tuple[Any, ...]], tmp_path: Path
) -> None:
    """The commit is the report's `Head:`, not the PR's head when it is posted: a push in between would otherwise get
    a review nobody gave. A finding's line outside the diff moves to the nearest diff line and says so; a file
    outside the diff goes in the review's body."""
    report = tmp_path / "report.md"
    report.write_text(REPORT)
    assert approvals.main(["verdict", "7", str(report)]) == 0
    (_, asked), (_, pr, review) = reviewing
    heading = "Verifier (claude, same-family), pass 2"
    assert (asked, pr) == ([(BASE, HEAD)], 7)
    assert review == {
        "commit_id": HEAD,
        "event": "COMMENT",
        "body": (
            f"{heading} on {HEAD[:7]}.\n\n"
            f"- **{heading} · S1** (minor): a file outside the diff, at `docs/old.md:3`, a file outside the diff\n\n"
            "The doc.\n\nVERDICT: 1 blocker, 0 major, 2 minor\nSATISFIED: no\nRisk: low — a test fixture\n"
        ),
        "comments": [
            {
                "path": "app.py",
                "line": 12,
                "side": "RIGHT",
                "body": f"**{heading} · C1** (blocker): a draft merges on its skipped checks\n\n- Failing input: a draft.",
            },
            {
                "path": "app.py",
                "line": 31,
                "side": "RIGHT",
                "body": (
                    f"**{heading} · C2** (minor): a line outside the diff\n\n"
                    "At `app.py:40`, outside the diff: placed at the nearest diff line.\n\nEvidence: the run."
                ),
            },
        ],
    }


@pytest.mark.parametrize(
    ("change", "why"),
    [
        (
            ("SATISFIED: no\n", ""),
            "has no `VERDICT:` or `SATISFIED:` line: the report is unfinished",
        ),
        ((f"Head: {HEAD}\n", ""), "has no `Head: <sha>` line naming the full commit it reviewed"),
        (
            (f"Head: {HEAD}\n", f"Head: {HEAD[:7]}\n"),
            "has no `Head: <sha>` line naming the full commit it reviewed",
        ),
        (
            ("Verifier: claude, same-family, pass 2\n", ""),
            "has no `Verifier: <family>, pass <n>` line",
        ),
    ],
)
def test_an_unfinished_report_posts_nothing(
    reviewing: list[tuple[Any, ...]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    change: tuple[str, str],
    why: str,
) -> None:
    report = tmp_path / "report.md"
    report.write_text(REPORT.replace(*change))
    assert approvals.main(["verdict", "7", str(report)]) == 1
    assert capsys.readouterr().out == f"{report} {why}\n"
    assert [call for call in reviewing if call[0] == "review"] == []


RANGED = f"""Verifier: claude, pass 1

## Correctness

### C1 (Major) app.py:9-11: a line range and a capitalised severity

```
$ grep x
# the line that matters
### quoted, not a finding
```

### C2 (minor) `app.py:28-29`: a range outside the diff

The run.

Head: {HEAD}
VERDICT: 0 blocker, 1 major, 1 minor
SATISFIED: no
Risk: low — a test fixture
"""


def test_a_finding_takes_a_line_range_any_case_severity_and_a_fenced_heading_in_its_evidence(
    reviewing: list[tuple[Any, ...]], tmp_path: Path
) -> None:
    """A range anchors at its last line, or the nearest diff line; a `#` line inside a code fence is evidence."""
    report = tmp_path / "report.md"
    report.write_text(RANGED)
    assert approvals.main(["verdict", "7", str(report)]) == 0
    heading = "Verifier (claude), pass 1"
    assert reviewing[-1][2]["comments"] == [
        {
            "path": "app.py",
            "line": 11,
            "side": "RIGHT",
            "body": (
                f"**{heading} · C1** (major): a line range and a capitalised severity\n\n"
                "```\n$ grep x\n# the line that matters\n### quoted, not a finding\n```"
            ),
        },
        {
            "path": "app.py",
            "line": 30,
            "side": "RIGHT",
            "body": (
                f"**{heading} · C2** (minor): a range outside the diff\n\n"
                "At `app.py:28-29`, outside the diff: placed at the nearest diff line.\n\nThe run."
            ),
        },
    ]


def test_a_finding_heading_verdict_cant_read_posts_nothing(
    reviewing: list[tuple[Any, ...]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A finding the review would leave out is no finding on the trail: refuse rather than drop it."""
    report = tmp_path / "report.md"
    report.write_text(REPORT.replace("### C2 (minor) app.py:40:", "### C2 (minor) app.py:"))
    assert approvals.main(["verdict", "7", str(report)]) == 1
    assert capsys.readouterr().out == (
        f"{report}: can't read the finding heading `### C2 (minor) app.py: a line outside the diff`: write it "
        "`### <id> (<blocker|major|minor>) <path>:<line>: <title>`\n"
    )
    assert [call for call in reviewing if call[0] == "review"] == []


# homelab PR #66's verifier pass 1, which `verdict` refused for its `### P1`..`### P4` sub-headings
SUBHEADED = f"""# PR #66 verifier report

Verifier: claude, same-family, pass 1

## Standards

None.

## Spec

Met.

## Correctness

### P1: root cause on live data and in window_check

Holds.

### P2: side effects of the 1d lookback

None.

### P3: window_check fails on main, passes on the head

Ran both.

### P4: the deploy step

Fine.

### M1 (minor) app.py:11: README says Agent loop spend uses the counters datasource "for every counter"

The README.

### P5: after a finding

Ends M1's body.

### Cron at 02:00 UTC skips the run

### P6: the 1:1 mapping holds

### Repro: `curl localhost:8080/health`

### P7 02:00 run skipped

### Instance on localhost:8000

### Repro on node:20 at 2026-10-21T02:00:00Z

Head: {HEAD}
VERDICT: 0 blocker, 0 major, 1 minor
SATISFIED: yes
Risk: low — a test fixture
"""


def test_a_sub_heading_that_is_no_finding_is_left_out_of_the_review(
    reviewing: list[tuple[Any, ...]], tmp_path: Path
) -> None:
    """Verifiers split Correctness into `###` sub-headings; one that doesn't read as a finding, with no
    `(<severity>)` in it, posts nothing and ends the finding above it, whatever times or ports it names."""
    report = tmp_path / "report.md"
    report.write_text(SUBHEADED)
    assert approvals.main(["verdict", "7", str(report)]) == 0
    heading = "Verifier (claude, same-family), pass 1"
    assert reviewing[-1][2]["comments"] == [
        {
            "path": "app.py",
            "line": 11,
            "side": "RIGHT",
            "body": (
                f"**{heading} · M1** (minor): README says Agent loop spend uses the counters datasource "
                '"for every counter"\n\nThe README.'
            ),
        }
    ]


@pytest.mark.parametrize(
    "broken",
    [
        "### C2 app.py:40: a line outside the diff",
        "### C2 minor app.py:40: a line outside the diff",
        "### C2 [minor] `app.py:40`: a line outside the diff",
        "### C2 [minor] **app.py:40**: a line outside the diff",
        "### C2 (nit) Makefile:40: a line outside the diff",
        "### app.py:40: a line outside the diff",
        "**C2 (minor) app.py:40: a line outside the diff**",
    ],
)
def test_a_finding_verdict_cant_read_leaves_the_counts_short_and_posts_nothing(
    reviewing: list[tuple[Any, ...]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    broken: str,
) -> None:
    """Whatever shape a finding's heading takes, `VERDICT:` still counts it: a report whose finding headings fall
    short of its counts is refused, never posted with that finding dropped."""
    report = tmp_path / "report.md"
    report.write_text(REPORT.replace("### C2 (minor) app.py:40: a line outside the diff", broken))
    assert approvals.main(["verdict", "7", str(report)]) == 1
    assert capsys.readouterr().out == (
        f"{report}: `VERDICT: 1 blocker, 0 major, 2 minor` counts 3 findings, but 2 headings read as one "
        "(1 blocker, 0 major, 1 minor): write each `### <id> (<blocker|major|minor>) <path>:<line>: <title>`\n"
    )
    assert [call for call in reviewing if call[0] == "review"] == []


def test_a_verdict_line_without_all_three_counts_posts_nothing(
    reviewing: list[tuple[Any, ...]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        REPORT.replace("VERDICT: 1 blocker, 0 major, 2 minor", "VERDICT: 1 blocker, 2 minor")
    )
    assert approvals.main(["verdict", "7", str(report)]) == 1
    assert capsys.readouterr().out == (
        f"{report}: write the verdict `VERDICT: <n> blocker, <n> major, <n> minor`\n"
    )
    assert [call for call in reviewing if call[0] == "review"] == []


def test_the_diffs_commentable_lines_are_the_new_side_of_each_hunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch = "@@ -1,3 +1,4 @@\n one\n-two\n+2\n+2b\n three\n@@ -20 +21,2 @@\n+x\n y"
    files = [{"filename": "a.py", "patch": patch}, {"filename": "logo.png", "patch": None}]
    monkeypatch.setattr(
        approvals,
        "gh",
        lambda *args, data=None: "".join(json.dumps(entry) + "\n" for entry in files),
    )
    assert approvals.diff_lines(BASE, HEAD) == {"a.py": [1, 2, 3, 4, 21, 22], "logo.png": []}


# --- the verifier's reviews that let a PR land ---

OLD = "c" * 40


def verified(
    *reviews: dict[str, Any], files: tuple[str, ...] = ("app.py",), **fields: Any
) -> list[str]:
    pr = pull(reviews=reviews, files=files, **fields)
    return approvals.proofs("merge", pr, [approved(1, "area:web")], LOOP)


@pytest.mark.parametrize(
    ("review", "line"),
    [
        (
            verdict_on(HEAD, satisfied="no"),
            f"PR #7: a verifier review on {HEAD} is not satisfied: fix and verify again",
        ),
        (
            verdict_on(HEAD, "1 blocker, 0 major, 0 minor"),
            f"PR #7: the verifier reviews on {HEAD} have 1 blocker and 0 major open: fix and verify again",
        ),
        (
            verdict_on(HEAD, "0 blockers, 2 majors, 0 minor"),
            f"PR #7: the verifier reviews on {HEAD} have 0 blocker and 2 major open: fix and verify again",
        ),
        (
            {**verdict_on(HEAD), "body": "Verifier (claude), pass 1\n\nSATISFIED: yes\n"},
            "PR #7: a verifier review lacks its commit, or a `VERDICT:` or `SATISFIED:` line (approvals.py verdict)",
        ),
        (
            {**verdict_on(HEAD), "commit": None},
            "PR #7: a verifier review lacks its commit, or a `VERDICT:` or `SATISFIED:` line (approvals.py verdict)",
        ),
    ],
)
def test_a_review_unsatisfied_or_with_a_blocker_or_major_open_lets_nothing_land(
    review: dict[str, Any], line: str
) -> None:
    assert verified(review) == [line]
    assert verified(VERDICT, review) == [line]


def test_no_verifier_review_lets_nothing_land() -> None:
    other = {**VERDICT, "body": "Looks fine.\n\nSATISFIED: yes\n"}
    assert verified(other) == ["PR #7: no verifier review posted (approvals.py verdict)"]
    assert verified(verdict_on(HEAD, heading="Verifier (claude, same-family), pass 3")) == []


def test_every_verifier_review_on_the_newest_passs_commit_must_be_satisfied() -> None:
    """A mixed PR's two verifiers review one commit: the second's satisfied review leaves the first's blocker open."""
    blocked = verdict_on(
        HEAD, "1 blocker, 0 major, 0 minor", satisfied="no", heading="Verifier (codex), pass 1"
    )
    assert verified(blocked, VERDICT) == [
        f"PR #7: a verifier review on {HEAD} is not satisfied: fix and verify again",
        f"PR #7: the verifier reviews on {HEAD} have 1 blocker and 0 major open: fix and verify again",
    ]
    # a pass on a later commit supersedes those on an earlier one, whichever family wrote either
    assert verified(verdict_on(OLD, "1 blocker, 0 major, 0 minor", satisfied="no"), VERDICT) == []
    codex = verdict_on(
        OLD, "1 blocker, 0 major, 0 minor", satisfied="no", heading="Verifier (codex), pass 1"
    )
    claude = verdict_on(HEAD, heading="Verifier (claude, same-family), pass 2")
    assert verified(codex, claude) == []


def test_a_later_pass_on_the_same_commit_supersedes_an_earlier_one() -> None:
    """Pass 1's major, triaged as theoretical with no commit after it, is accepted by pass 2 on the same head; a mixed
    PR's two verifiers share a pass number, so both of pass 2's reviews still count."""
    rejected = verdict_on(
        HEAD,
        "0 blocker, 1 major, 0 minor",
        satisfied="no",
        heading="Verifier (claude, same-family), pass 1",
    )
    accepted = verdict_on(HEAD, heading="Verifier (claude, same-family), pass 2")
    assert verified(rejected, accepted) == []
    codex = verdict_on(
        HEAD, "1 blocker, 0 major, 0 minor", satisfied="no", heading="Verifier (codex), pass 2"
    )
    assert verified(rejected, codex, accepted) == [
        f"PR #7: a verifier review on {HEAD} is not satisfied: fix and verify again",
        f"PR #7: the verifier reviews on {HEAD} have 1 blocker and 0 major open: fix and verify again",
    ]


def test_a_review_on_an_older_commit_never_covers_the_head() -> None:
    """Every commit after a verdict needs one of its own, a merge of main that touches no PR file included."""
    line = (
        f"PR #7: the newest verifier review is on {OLD}, not on the head {HEAD}:"
        " every commit after a verdict needs a verdict of its own"
    )
    assert verified(verdict_on(OLD)) == [line]
    assert verified(verdict_on(OLD), files=("README.md",)) == [line]
    # a comment after the verdict is no verdict
    assert verified(verdict_on(OLD), comments=("Triaged: fixed in the head, lands.",)) == [line]


def capped(*reviews: dict[str, Any], loop: str = "- spec: always\n", **fields: Any) -> list[str]:
    """owner_waits on a project whose loop.md has no `merge:` rule: only the cap asks for the owner's label."""
    return approvals.owner_waits(pull(reviews=reviews, files=("app.py",), **fields), [], loop)


def test_a_core_finding_open_at_the_cap_waits_for_the_owner_even_after_a_satisfied_pass() -> None:
    """Pass 5 left a major open: only the owner decides the fix, so the scoped pass 6 lands on their label."""
    open_at_cap = verdict_on(
        OLD, "0 blocker, 1 major, 0 minor", satisfied="no", heading="Verifier (claude), pass 5"
    )
    pass6 = verdict_on(HEAD, heading="Verifier (claude), pass 6")
    assert verified(open_at_cap, pass6) == []
    assert capped(open_at_cap, pass6) == [
        (
            HELD + "a verifier review at the cap (pass 5) or later"
            " was not satisfied or left a blocker or major open, so the owner decides"
        )
    ]
    assert capped(open_at_cap, pass6, labels=OWNED) == []
    stale = capped(open_at_cap, pass6, labels=OWNED, labeled="2026-10-01T09:00:00Z")
    assert stale == [
        "PR #7: `approved:merge` was added before the head was pushed: the owner adds it again"
    ]


@pytest.mark.parametrize(
    ("counts", "satisfied"),
    [("0 blocker, 1 major, 0 minor", "yes"), ("0 blocker, 0 major, 0 minor", "no")],
)
def test_a_review_at_the_cap_holds_on_a_core_finding_or_on_not_being_satisfied(
    counts: str, satisfied: str
) -> None:
    at_cap = verdict_on(OLD, counts, satisfied=satisfied, heading="Verifier (claude), pass 5")
    assert capped(at_cap, verdict_on(HEAD, heading="Verifier (claude), pass 6")) != []


def test_minors_only_at_the_cap_or_core_findings_before_it_need_no_owner() -> None:
    minors = verdict_on(HEAD, "0 blocker, 0 major, 3 minor", heading="Verifier (claude), pass 5")
    assert capped(minors) == []
    early = verdict_on(
        OLD, "1 blocker, 0 major, 0 minor", satisfied="no", heading="Verifier (claude), pass 4"
    )
    assert capped(early, verdict_on(HEAD, heading="Verifier (claude), pass 5")) == []


def test_the_cap_is_skills_default_unless_the_projects_loop_md_sets_its_own() -> None:
    assert approvals.cap(None) == approvals.cap("- spec: always\n") == 5  # SKILL.md § The cap
    assert approvals.cap("## Loop\n\n- cap: 3\n") == approvals.cap("`cap: 3`") == 3
    assert approvals.cap("- cap: 3 (reviews are expensive here)\n") == 3
    for unread in ("- cap: 3 passes\n", "- Cap: three\n"):
        with pytest.raises(approvals.Refused, match="not `cap: <n>`"):
            approvals.cap(unread)
    major = verdict_on(
        OLD, "0 blocker, 1 major, 0 minor", satisfied="no", heading="Verifier (claude), pass 3"
    )
    later = verdict_on(HEAD, heading="Verifier (claude), pass 4")
    assert capped(major, later) == []
    assert capped(major, later, loop="- cap: 3\n") == [
        (
            HELD + "a verifier review at the cap (pass 3) or later"
            " was not satisfied or left a blocker or major open, so the owner decides"
        )
    ]


def test_only_a_review_by_the_prs_author_or_the_viewer_counts(
    monkeypatch: pytest.MonkeyPatch, writers: list[str]
) -> None:
    """Anyone can review a public repo; a stranger's satisfied review is no verifier review."""
    stranger = verdict_on(HEAD, author="stranger")
    blocked = verdict_on(HEAD, "1 blocker, 0 major, 0 minor", satisfied="no")
    assert verified(stranger) == ["PR #7: no verifier review posted (approvals.py verdict)"]
    assert verified(blocked, stranger) == verified(blocked)
    assert verified(verdict_on(HEAD, author="worker")) == []  # the PR's author
    monkeypatch.setattr(approvals, "viewer", lambda: "coordinator")
    assert verified(verdict_on(HEAD, author="coordinator")) == []
    assert verified(verdict_on(HEAD, author=None)) == [  # a deleted account
        "PR #7: no verifier review posted (approvals.py verdict)"
    ]


def test_a_writers_review_counts_with_an_installation_token(
    monkeypatch: pytest.MonkeyPatch, writers: list[str]
) -> None:
    """A colleague who can write to the repo verifies someone else's PR and posts the verdict as themself: CI, with no
    viewer, counts it; a stranger's still doesn't."""
    monkeypatch.setattr(approvals, "viewer", lambda: None)

    def proofs(review: dict[str, Any]) -> list[str]:
        pr = {
            **pull(reviews=(review,), files=("app.py",)),
            "author": {"__typename": "User", "login": "author"},
        }
        return approvals.proofs("merge", pr, [approved(1, "area:web")], LOOP)

    assert proofs(verdict_on(HEAD, author="worker")) == []
    assert proofs(verdict_on(HEAD, author="stranger")) == [
        "PR #7: no verifier review posted (approvals.py verdict)"
    ]
    assert writers == ["worker", "stranger"]


def test_without_a_user_token_the_prs_author_and_writers_reviews_count(
    monkeypatch: pytest.MonkeyPatch, writers: list[str]
) -> None:
    """An installation token (the approvals workflow's `github.token`) can't read `GET /user`: the gate trusts the
    PR's author and the repo's writers instead of failing every PR with a verifier review."""

    def gh(*args: str, data: str | None = None) -> str:
        assert args[:2] == ("api", "user"), args
        raise subprocess.CalledProcessError(
            1, "gh", stderr="gh: Resource not accessible by integration (HTTP 403)\n"
        )

    monkeypatch.setattr(approvals, "gh", gh)
    monkeypatch.setattr(approvals, "viewer", VIEWER)
    assert approvals.viewer() is None
    assert verified(verdict_on(HEAD, author="worker")) == []
    assert verified(verdict_on(HEAD, author="loop")) == [
        "PR #7: no verifier review posted (approvals.py verdict)"
    ]


def test_a_review_requesting_changes_lets_nothing_land() -> None:
    assert verified(VERDICT, latest=("CHANGES_REQUESTED", "APPROVED")) == [
        "PR #7: reviewer requested changes: answer the review"
    ]
    assert verified(VERDICT, latest=("APPROVED", "COMMENTED")) == []


def test_an_unresolved_review_thread_lets_nothing_land() -> None:
    assert verified(VERDICT, threads=(True, False, False)) == [
        "PR #7: 2 review thread(s) unresolved: fix and reply, or triage, then resolve (github.md, Review trail)"
    ]
    assert verified(VERDICT, threads=(True, True)) == []


BOTS = LOOP + "- bot: dependabot[bot] path uv.lock or path `**/package.json`\n"
UNREVIEWED = ["PR #7: no verifier review posted (approvals.py verdict)"]


def authored(login: str | None, committer: str | None = None) -> dict[str, Any]:
    """A commit on the PR as GraphQL's `authored` returns it, by `login` (None: no GitHub account), committed by
    `committer` (None: no account, as GitHub's web-flow committer on a bot's own commits)."""
    return {
        "commit": {
            "authors": {"nodes": [{"user": {"login": login} if login else None}]},
            "committer": {"user": {"login": committer} if committer else None},
        }
    }


@pytest.mark.parametrize(
    "login", ["dependabot", "dependabot[bot]"]
)  # GraphQL's spelling, and REST's
def test_an_allow_listed_bots_lock_or_manifest_only_pr_needs_no_verifier_review(login: str) -> None:
    def made(
        files: tuple[str, ...] = ("uv.lock",),
        who: str = login,
        kind: str = "Bot",
        commits: tuple[str | None, ...] = ("dependabot[bot]",),
    ) -> dict[str, Any]:
        pr = {**pull(files=files), "author": {"__typename": kind, "login": who}}
        pr["authored"] = {"nodes": [authored(by) for by in commits]}
        return pr

    def bot(*files: str, loop: str = BOTS, **fields: Any) -> list[str]:
        return approvals.proofs("merge", made(files or ("uv.lock",), **fields), [], loop)

    def gate(pr: dict[str, Any]) -> list[str]:
        return approvals.proofs("merge", pr, [], BOTS)

    assert bot("uv.lock", "web/package.json") == []
    assert bot("uv.lock", "app.py") == UNREVIEWED  # code needs a review as usual
    assert bot(who="renovate") == UNREVIEWED  # a bot the line doesn't name
    assert bot(kind="User") == UNREVIEWED  # a person is never the bot
    assert bot(loop=LOOP) == UNREVIEWED  # no `bot:` line: no exemption
    assert approvals.proofs("merge", made(files=()), [], BOTS) == UNREVIEWED
    assert bot(commits=("dependabot", "dependabot[bot]")) == []
    assert bot(commits=("dependabot[bot]", "worker")) == UNREVIEWED  # a person's push
    assert bot(commits=(None,)) == UNREVIEWED  # an author GitHub ties to no account
    assert bot(commits=()) == UNREVIEWED
    unread = BOTS.replace("path uv.lock or", "lock files or path uv.lock or")
    assert bot(loop=unread) == UNREVIEWED  # a condition the gate can't read
    for change in (
        "RENAMED",
        "COPIED",
    ):  # app.py moved or copied onto uv.lock: GraphQL shows only uv.lock
        moved = made()
        moved["files"]["nodes"][0]["changeType"] = change
        assert gate(moved) == UNREVIEWED
    crowded = made(files=("uv.lock",) * 100)
    crowded["files"]["totalCount"] = 101  # past the one page of files the gate reads
    assert gate(crowded) == UNREVIEWED
    long = made(commits=("dependabot[bot]",) * 100)
    long["authored"]["totalCount"] = 101  # past the one page of commits the gate reads
    assert gate(long) == UNREVIEWED
    shared = made()
    shared["authored"]["nodes"][0]["commit"]["authors"] = {
        "totalCount": 6,  # a sixth co-author past the five the gate reads
        "nodes": [{"user": {"login": "dependabot[bot]"}}] * 5,
    }
    assert gate(shared) == UNREVIEWED
    rebased = made()
    rebased["authored"]["nodes"] = [authored("dependabot[bot]", committer="worker")]
    assert gate(rebased) == UNREVIEWED  # a person's rebase keeps the bot as author
    signed = made()
    signed["authored"]["nodes"] = [authored("dependabot[bot]", committer="dependabot[bot]")]
    assert gate(signed) == []
    assert approvals.risk_rules(BOTS) == approvals.risk_rules(LOOP)  # a bot line is no risk rule


def test_more_reviews_or_threads_than_one_page_is_refused() -> None:
    crowded = pull(reviews=(VERDICT,), threads=(True,))
    crowded["reviews"]["totalCount"] = 101
    crowded["reviewThreads"]["totalCount"] = 101
    assert approvals.proofs("merge", crowded, [approved(1, "area:web")], LOOP) == [
        "PR #7 has more than 1 reviews: the gate reads one page",
        "PR #7 has more than 1 review threads: the gate reads one page",
    ]


# --- merge: rules ---

GITHUB_RULE = "## Approvals\n\n- merge: path `.github/**`\n"


def test_a_merge_path_rule_asks_for_the_label_only_on_a_pr_touching_its_path() -> None:
    def waits(loop: str, *files: str, total: int | None = None) -> list[str]:
        pr = pull(reviews=(VERDICT,), files=files)
        if total is not None:
            pr["files"]["totalCount"] = total
        return approvals.waits(pr, [approved(1, "area:web")], loop)

    unjudged = HELD + "a risk rule the gate can't judge holds until a person does"
    assert waits(GITHUB_RULE, ".github/ci.yml") == [GITHUB]
    assert waits(GITHUB_RULE, "README.md") == []
    # files the gate can't read
    assert waits(GITHUB_RULE, "README.md", total=101) == [f"{unjudged} (path `.github/**`)"]
    assert waits("## Approvals\n\n- risk: a schema change\n", "README.md") == [
        f"{unjudged} (a schema change)"
    ]
    assert waits("## Approvals\n\n- merge: component `web`\n", "README.md") == [
        HELD + "it matches a risk rule (component `web`)"
    ]
    assert waits("## Approvals\n\n- merge: category ops\n", "README.md") == []


# --- land ---


@pytest.fixture
def landing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """`land` in a checkout with the fixture's tracker and a `merge: path .github/**` rule, against a stubbed GitHub:
    the PR (one approved issue, a verdict on the head, `check` green, a draft), the checks the base's rulesets and
    branch protection require, whether the repo allows auto-merge; `calls` holds each `gh pr` command."""
    agents = tmp_path / "docs" / "agents"
    agents.mkdir(parents=True)
    (agents / "issue-tracker.md").write_text(TRACKER)
    (agents / "loop.md").write_text(GITHUB_RULE)
    pr = pull(reviews=(VERDICT,), files=("app.py",))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    state: dict[str, Any] = {
        "pull": pr,
        "rulesets": ["check"],
        "protection": [],
        "auto": True,
        "calls": [],
        "run": {"status": "completed", "url": "https://github.com/o/r/actions/runs/12345"},
    }

    def gh(*args: str, data: str | None = None) -> str:
        if args[:2] == ("run", "view"):
            state["calls"].append(args[:3])
            if state["run"] is None:
                raise subprocess.CalledProcessError(
                    1, args, stderr="failed to get run: HTTP 404: Not Found"
                )
            return json.dumps(state["run"])
        if args[0] in ("pr", "run"):
            state["calls"].append(args)
            return ""
        if args[:2] == ("api", "--paginate") and args[2].endswith("/rules/branches/main"):
            if isinstance(state["rulesets"], Exception):
                raise state["rulesets"]
            return "".join(f"{name}\n" for name in state["rulesets"])
        if args[1] == "repos/{owner}/{repo}/branches/main":
            return "".join(f"{name}\n" for name in state["protection"])
        if args[1:] == ("repos/{owner}/{repo}", "--jq", ".allow_auto_merge"):
            return f"{str(state['auto']).lower()}\n"
        raise AssertionError(args)

    monkeypatch.setattr(approvals, "gh", gh)
    monkeypatch.setattr(approvals, "pull_request", lambda _n: state["pull"])
    monkeypatch.chdir(tmp_path)
    return state


def landed(
    capsys: pytest.CaptureFixture[str], landing: dict[str, Any]
) -> tuple[int, list[str], list[tuple[str, ...]]]:
    code = approvals.main(["land", "7"])
    return code, capsys.readouterr().out.splitlines(), landing["calls"]


READY = ("pr", "ready", "7")
MERGE = ("pr", "merge", "7", "--squash", "--match-head-commit", HEAD)


def test_land_merges_a_proven_ready_pr_at_its_head(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert landed(capsys, landing) == (0, [f"PR #7 merges at {HEAD}"], [MERGE])


def test_land_marks_a_proven_draft_ready_and_waits_for_the_ci_that_starts(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """A draft's checks are skipped (CI skips drafts) and say nothing about the ready PR: no merge, no auto-merge."""
    landing["pull"]["isDraft"] = True
    landing["pull"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"] = [
        {"__typename": "CheckRun", "name": "check", "status": "COMPLETED", "conclusion": "SKIPPED"}
    ]
    for rulesets in (["check"], []):
        landing["calls"].clear()
        landing["rulesets"] = rulesets
        assert landed(capsys, landing) == (
            approvals.WAITING,
            ["PR #7 is ready now: CI starts on ready, run land again"],
            [READY],
        )


def test_land_run_again_before_the_ready_prs_ci_registers_waits_for_it(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """The head still holds only the draft's skipped run, which GitHub counts as passing: a skipped run completed
    before the newest ready-for-review is the draft's, and says nothing about the ready PR."""
    ready = "2026-10-01T12:00:00Z"
    landing["pull"]["timelineItems"]["nodes"].append(
        {"__typename": "ReadyForReviewEvent", "createdAt": ready}
    )
    rollup = landing["pull"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]
    draft = {
        "__typename": "CheckRun",
        "name": "check",
        "status": "COMPLETED",
        "conclusion": "SKIPPED",
        "completedAt": "2026-10-01T11:30:00Z",
    }
    for rulesets in (["check"], []):
        landing["calls"].clear()
        landing["rulesets"] = rulesets
        rollup["nodes"] = [draft]
        code, lines, calls = landed(capsys, landing)
        assert (code, calls) == (approvals.WAITING, [])
        assert lines == [WAITED]
        # a run that completed on the draft is the head's result: a workflow need not run again on ready
        rollup["nodes"] = [{**draft, "conclusion": "SUCCESS"}]
        landing["calls"].clear()
        assert landed(capsys, landing) == (0, [f"PR #7 merges at {HEAD}"], [MERGE])
        rollup["nodes"] = [
            draft,
            {**draft, "conclusion": "SKIPPED", "completedAt": "2026-10-01T12:00:01Z"},
        ]
        landing["calls"].clear()
        assert landed(capsys, landing) == (0, [f"PR #7 merges at {HEAD}"], [MERGE])
    # a base requiring none: another check that ran on the draft doesn't stand in for the skipped one
    landing["calls"].clear()
    rollup["nodes"] = [draft, {**draft, "name": "lint", "conclusion": "SUCCESS"}]
    code, lines, calls = landed(capsys, landing)
    assert (code, lines, calls) == (
        approvals.WAITING,
        [WAITED],
        [],
    )


def test_land_merges_past_a_draft_only_check_its_workflows_finished_run_never_produced(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """A matrix job skipped on the draft before its matrix expanded leaves a check named literally `matrix.part`,
    which the ready PR's run, expanding it to `check:lint`, never produces. On a base requiring no check, `land`
    waits for every check; that one is gone once its workflow's run since ready has finished, and not before, since
    a job that needs another has no check run until it starts."""
    ready = "2026-10-01T12:00:00Z"
    landing["pull"]["timelineItems"]["nodes"].append(
        {"__typename": "ReadyForReviewEvent", "createdAt": ready}
    )
    landing["rulesets"] = []

    def run(
        name: str, conclusion: str | None, at: str, suite: str, flow: str = "CI"
    ) -> dict[str, Any]:
        return {
            "__typename": "CheckRun",
            "name": name,
            "status": "COMPLETED" if conclusion else "IN_PROGRESS",
            "conclusion": conclusion,
            "startedAt": at,
            "completedAt": at if conclusion else None,
            "checkSuite": {"status": suite, "workflowRun": {"workflow": {"name": flow}}},
        }

    draft = run("matrix.part", "SKIPPED", "2026-10-01T11:30:00Z", "COMPLETED")
    after = "2026-10-01T12:01:00Z"
    waited = WAITED.replace("`check`", "`matrix.part`")
    rollup = landing["pull"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]
    # the run since ready is still going: `check`, which needs the parts, has no check run yet
    rollup["nodes"] = [draft, run("check:lint", "SUCCESS", after, "IN_PROGRESS")]
    assert landed(capsys, landing) == (approvals.WAITING, [waited], [])
    rollup["nodes"] = [
        draft,
        run("check:lint", "SUCCESS", after, "COMPLETED"),
        run("check", "SUCCESS", after, "COMPLETED"),
    ]
    assert landed(capsys, landing) == (0, [f"PR #7 merges at {HEAD}"], [MERGE])
    # another workflow's finished run says nothing about whether CI still produces the name
    landing["calls"].clear()
    rollup["nodes"] = [draft, run("lint", "SUCCESS", after, "COMPLETED", "Lint")]
    assert landed(capsys, landing) == (approvals.WAITING, [waited], [])
    # GitHub may start a skipped run after it completed, so after a ready right behind it: still the draft's run
    rollup["nodes"] = [
        {**draft, "startedAt": "2026-10-01T12:00:10Z"},
        run("lint", "SUCCESS", after, "COMPLETED", "Lint"),
    ]
    assert landed(capsys, landing) == (approvals.WAITING, [waited], [])
    # one name in two workflows waits until each has finished a run since ready, in either order
    other = {
        **draft,
        "checkSuite": {"status": "COMPLETED", "workflowRun": {"workflow": {"name": "Lint"}}},
    }
    for nodes in ([draft, other], [other, draft]):
        rollup["nodes"] = [*nodes, run("lint", "SUCCESS", after, "COMPLETED", "Lint")]
        assert landed(capsys, landing) == (approvals.WAITING, [waited], [])
        # nor does the other workflow's ready run of that very name stand in for this one's
        rollup["nodes"] = [
            *({**node, "name": "check"} for node in nodes),
            run("check", "SUCCESS", after, "COMPLETED", "Lint"),
        ]
        assert landed(capsys, landing) == (approvals.WAITING, [WAITED], [])


def test_land_waits_on_a_head_with_no_checks_at_all(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """GitHub gives a head no check ran on (a path filter skipped CI) a null rollup."""
    landing["pull"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"] = None
    for rulesets, wanted in ((["check"], "`check`"), ([], "check")):
        landing["rulesets"] = rulesets
        assert landed(capsys, landing) == (
            approvals.WAITING,
            [f"PR #7: no {wanted} on the head commit yet"],
            [],
        )


def test_land_turns_on_auto_merge_while_required_checks_are_pending(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"] = {
        **landing["pull"],
        **pull(reviews=(VERDICT,), checks=(("check", "IN_PROGRESS"),)),
    }
    landing["pull"]["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    assert landed(capsys, landing) == (
        0,
        [f"PR #7: auto-merge on at {HEAD}, once check pass"],
        [(*MERGE, "--auto")],
    )


@pytest.mark.parametrize(
    ("change", "line"),
    [
        ({"auto": False}, "PR #7: `check` is IN_PROGRESS on the head commit"),
        ({"rulesets": []}, "PR #7: `check` is IN_PROGRESS on the head commit"),
        ({"state": "FAILURE"}, "PR #7: `check` is FAILURE on the head commit"),
        ({"files": (".github/ci.yml",)}, GITHUB),
    ],
)
def test_land_waits_without_auto_merge_where_github_would_not_hold_the_merge(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str], change: dict[str, Any], line: str
) -> None:
    """Auto-merge only while the base's required checks are pending: not where the repo forbids it, the base
    requires none, a required check is red, or the owner's label is asked for, which GitHub would not wait for."""
    checks = (("check", change.pop("state", "IN_PROGRESS")), ("lint", "FAILURE"))
    pr = pull(reviews=(VERDICT,), checks=checks, files=change.pop("files", ("app.py",)))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    landing.update(change, pull=pr)
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (approvals.WAITING, [])
    assert line in lines


def rules_error(status: int, message: str) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(
        1, ("gh", "api"), stderr=f"gh: {message} (HTTP {status})\n"
    )


FREE_PLAN = "Upgrade to GitHub Pro or make this repository public to enable this feature."


def test_land_on_a_free_plan_private_repo_merges_at_the_head_and_says_github_enforces_nothing(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """GitHub's free plan has no rulesets on a private repo, nor auto-merge: its 403 reads as no required checks."""
    landing["rulesets"] = rules_error(403, FREE_PLAN)
    enforces = (
        "GitHub enforces no rules on main here (its plan has none): land's proofs are the only gate"
    )
    assert landed(capsys, landing) == (0, [enforces, f"PR #7 merges at {HEAD}"], [MERGE])
    # a check still pending waits for the next run, never for auto-merge
    landing["pull"] = {
        **landing["pull"],
        **pull(reviews=(VERDICT,), checks=(("check", "IN_PROGRESS"),)),
    }
    landing["pull"]["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    landing["calls"].clear()
    code, lines, calls = landed(capsys, landing)
    assert (code, lines[0], calls) == (approvals.WAITING, enforces, [])


@pytest.mark.parametrize(
    "error",
    [rules_error(403, "Resource not accessible by integration"), rules_error(404, "Not Found")],
)
def test_land_fails_on_any_other_rules_error(
    landing: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    error: subprocess.CalledProcessError,
) -> None:
    landing["rulesets"] = error
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (1, [])
    assert not any("enforces" in line for line in lines)


def test_a_base_with_no_required_checks_gets_no_auto_merge_while_a_check_is_pending(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """GitHub would merge an auto-merge request at once on a base that requires nothing, pending checks or not."""
    landing["rulesets"] = []
    pr = pull(reviews=(VERDICT,), checks=(("check", "IN_PROGRESS"),))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    landing["pull"] = pr
    assert landed(capsys, landing) == (
        approvals.WAITING,
        ["PR #7: `check` is IN_PROGRESS on the head commit"],
        [],
    )


def test_a_base_with_no_required_checks_needs_every_check_green(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["rulesets"] = []
    pr = pull(reviews=(VERDICT,), checks=(("check", "SUCCESS"), ("pr-board / sync", "FAILURE")))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    landing["pull"] = pr
    assert landed(capsys, landing) == (
        approvals.WAITING,
        ["PR #7: `pr-board / sync` is FAILURE on the head commit"],
        [],
    )
    assert approvals.ci("PR #7", pull(checks=()), set()) == [
        "PR #7: no check on the head commit yet"
    ]
    assert approvals.ci("PR #7", pull(checks=(("lint", "SUCCESS"),)), set()) == []


def test_the_required_checks_are_the_rulesets_and_the_branch_protections(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing.update(rulesets=["check", "loop:approvals"], protection=["qualify"])
    assert approvals.required_checks("main") == {"check", "loop:approvals", "qualify"}
    landing["rulesets"] = []
    pr = pull(reviews=(VERDICT,), checks=(("check", "SUCCESS"), ("qualify", "QUEUED")))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    landing["pull"] = pr
    assert landed(capsys, landing)[2] == [(*MERGE, "--auto")]


RUN_URL = "https://github.com/kzarzycki/scratch-gate-revert/actions/runs/12345/job/678"


def approvals_red(
    landing: dict[str, Any], url: str | None = RUN_URL, state: str = "FAILURE", **change: Any
) -> dict[str, Any]:
    """A proven ready PR whose required `loop:approvals` status is the FAILURE the approvals workflow posted while a
    review thread was open; resolving the thread fired no workflow."""
    landing["rulesets"] = ["check", "loop:approvals"]
    pr = pull(**{"reviews": (VERDICT,), "files": ("app.py",), **change})
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"].append(
        {
            "__typename": "StatusContext",
            "context": "loop:approvals",
            "state": state,
            "createdAt": "2026-10-03T13:00:00Z",
            "targetUrl": url,
        }
    )
    landing["pull"] = pr
    return pr


def test_land_reruns_the_approvals_run_left_red_when_only_it_blocks_a_proven_pr(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    approvals_red(landing)
    assert landed(capsys, landing) == (
        approvals.WAITING,
        [
            (
                "PR #7: every proof holds but `loop:approvals` is FAILURE on the head commit: reran run 12345,"
                " since resolving a review thread starts no workflow; run land again"
            )
        ],
        [("run", "view", "12345"), ("run", "rerun", "12345")],
    )


def test_land_waits_without_a_rerun_while_the_approvals_run_still_runs(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    approvals_red(landing)
    landing["run"]["status"] = "in_progress"
    assert landed(capsys, landing) == (
        approvals.WAITING,
        [
            (
                "PR #7: every proof holds but `loop:approvals` is FAILURE on the head commit: its run 12345 is"
                " in_progress, so the status is not posted yet; run land again"
            )
        ],
        [("run", "view", "12345")],
    )


def test_land_never_reruns_a_run_this_repo_does_not_have(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    approvals_red(landing, "https://github.com/someone/else/actions/runs/1")
    landing["run"] = None
    assert landed(capsys, landing) == (
        approvals.WAITING,
        [
            (
                "PR #7: every proof holds but `loop:approvals` is FAILURE on the head commit, and its target names"
                " no Actions run of this repo: rerun the workflow that posts it, then run land again"
            )
        ],
        [("run", "view", "1")],
    )


def test_land_never_reruns_a_check_run_named_like_the_approvals_status(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["rulesets"] = ["check", "loop:approvals"]
    pr = pull(
        reviews=(VERDICT,),
        files=("app.py",),
        checks=(("check", "SUCCESS"), ("loop:approvals", "FAILURE")),
    )
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    landing["pull"] = pr
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (approvals.WAITING, [])
    assert "PR #7: `loop:approvals` is FAILURE on the head commit" in lines


def test_land_never_reruns_the_approvals_run_on_a_failed_proof(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    approvals_red(landing, threads=(False,))
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (1, [])
    assert any("review thread(s) unresolved" in line for line in lines)


@pytest.mark.parametrize(
    ("change", "line"),
    [
        ({"checks": (("check", "FAILURE"),)}, "PR #7: `check` is FAILURE on the head commit"),
        (
            {"checks": (("check", "IN_PROGRESS"),)},
            "PR #7: `check` is IN_PROGRESS on the head commit",
        ),
        ({"checks": ()}, "PR #7: no `check` on the head commit yet"),
        ({"files": (".github/ci.yml",)}, GITHUB),
        (
            {"state": "PENDING", "auto": False},
            "PR #7: `loop:approvals` is PENDING on the head commit",
        ),
        (
            {"loop": "- CI: none\n"},
            (
                "PR #7: the project has no CI (loop.md `CI: none`), and no local check passed on the head"
                " (approvals.py local-ci)"
            ),
        ),
    ],
)
def test_land_never_reruns_the_approvals_run_while_anything_else_waits(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str], change: dict[str, Any], line: str
) -> None:
    """Another required check red, pending or missing, the owner's label asked for, `loop:approvals` itself still
    pending where the repo allows no auto-merge, or a project without CI waiting on its local check: a rerun would not let the PR land, so land waits."""
    landing["auto"] = change.pop("auto", True)
    if "loop" in change:
        Path("docs/agents/loop.md").write_text(GITHUB_RULE + change.pop("loop"))
    approvals_red(landing, **change)
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (approvals.WAITING, [])
    assert line in lines


@pytest.mark.parametrize("url", [None, "", "https://example.com/approvals"])
def test_land_says_so_when_the_approvals_status_names_no_run(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str], url: str | None
) -> None:
    approvals_red(landing, url)
    assert landed(capsys, landing) == (
        approvals.WAITING,
        [
            (
                "PR #7: every proof holds but `loop:approvals` is FAILURE on the head commit, and the status names no"
                " Actions run to rerun: rerun the workflow that posts it, then run land again"
            )
        ],
        [],
    )


@pytest.mark.parametrize(
    ("change", "line"),
    [
        (
            {"reviews": (verdict_on(HEAD, satisfied="no"),)},
            f"PR #7: a verifier review on {HEAD} is not satisfied: fix and verify again",
        ),
        (
            {"reviews": (verdict_on(HEAD, "1 blocker, 0 major, 0 minor"),)},
            f"PR #7: the verifier reviews on {HEAD} have 1 blocker and 0 major open: fix and verify again",
        ),
        (
            {"reviews": (verdict_on(HEAD, "0 blocker, 1 major, 0 minor"),)},
            f"PR #7: the verifier reviews on {HEAD} have 0 blocker and 1 major open: fix and verify again",
        ),
        (
            {"reviews": (verdict_on(OLD),)},
            (
                f"PR #7: the newest verifier review is on {OLD}, not on the head {HEAD}:"
                " every commit after a verdict needs a verdict of its own"
            ),
        ),
        (
            {"latest": ("CHANGES_REQUESTED",)},
            "PR #7: reviewer requested changes: answer the review",
        ),
        (
            {"issue": issue(1, "area:web", "kind:bug", "size:S")},
            "#1 lacks the `approved:spec` label",
        ),
        ({"reviews": ()}, "PR #7: no verifier review posted (approvals.py verdict)"),
        (
            {"threads": (True, False)},
            "PR #7: 1 review thread(s) unresolved: fix and reply, or triage, then resolve (github.md, Review trail)",
        ),
    ],
)
def test_land_refuses_a_missing_proof_and_never_marks_the_pr_ready(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str], change: dict[str, Any], line: str
) -> None:
    found = change.pop("issue", approved(1, "area:web", "kind:bug"))
    pr = pull(**{"reviews": (VERDICT,), "files": ("app.py",), **change})
    pr["closingIssuesReferences"]["nodes"] = [found]
    landing["pull"] = pr
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (1, [])
    assert line in lines


def test_an_unreadable_cap_line_is_refused_before_any_proof_and_before_ready(
    landing: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A PR the risk rule already holds never reached the cap, so `check merge` printed its proofs and passed or
    waited, and `land` marked the draft ready. The bad `cap:` line now comes first, alone, and nothing reaches GitHub.
    """
    (tmp_path / "docs" / "agents" / "loop.md").write_text(GITHUB_RULE + "- cap: 3 passes\n")
    refused = ["loop.md has a `cap:` line that is not `cap: <n>`: write it as `- cap: <n>`"]
    risky = pull(reviews=(VERDICT,), files=(".github/ci.yml",), labels=("risk:high", *OWNED))
    risky["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    risky["isDraft"] = True
    landing["pull"] = risky
    assert landed(capsys, landing) == (1, refused, [])
    unverified = pull(files=(".github/ci.yml",), labels=("risk:high",))
    unverified["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    landing["pull"] = unverified
    assert approvals.main(["check", "merge", "7"]) == 1
    assert (capsys.readouterr().out.splitlines(), landing["calls"]) == (refused, [])


def test_land_says_a_merged_pr_is_merged_and_refuses_a_closed_one(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"]["state"] = "MERGED"
    assert landed(capsys, landing) == (0, ["PR #7 is merged"], [])
    landing["pull"]["state"] = "CLOSED"
    assert landed(capsys, landing) == (1, ["PR #7 is closed: nothing to land"], [])


# --- land --wait: one background command that ends at merged, refused, the owner or the ceiling ---


@pytest.fixture
def later(landing: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """`land --wait` against `landing`: each sleep moves the clock POLL seconds on, and GitHub's PR to the next one
    in this list (the last stays)."""
    states: list[dict[str, Any]] = []
    clock = [0.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds
        if states:
            landing["pull"] = states.pop(0)

    monkeypatch.setattr(approvals.time, "sleep", sleep)
    monkeypatch.setattr(approvals.time, "monotonic", lambda: clock[0])
    return states


def proven(check: str | None = "SUCCESS", **fields: Any) -> dict[str, Any]:
    """A proven PR whose `check` is in state `check` on the head (None: not there yet), with GitHub's fields changed."""
    files = fields.pop("files", ("app.py",))
    pr = pull(reviews=(VERDICT,), files=files, checks=(("check", check),) if check else ())
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    return {**pr, **fields}


def waited(
    capsys: pytest.CaptureFixture[str], landing: dict[str, Any]
) -> tuple[int, list[str], list[tuple[str, ...]]]:
    code = approvals.main(["land", "7", "--wait"])
    return code, capsys.readouterr().out.splitlines(), landing["calls"]


def test_land_wait_marks_a_draft_ready_and_merges_it_once_its_ci_is_green(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"] = proven("SKIPPED", isDraft=True)
    later += [proven(None), proven(None), proven("SUCCESS"), proven(state="MERGED")]
    assert waited(capsys, landing) == (
        0,
        [
            "PR #7 is ready now: CI starts on ready, run land again",
            "PR #7: no `check` on the head commit yet",  # printed once for its two reads
            f"PR #7 merges at {HEAD}",
            "PR #7 is merged",
        ],
        [READY, MERGE],
    )


def test_land_wait_follows_a_merge_github_queues_until_it_merges(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    """On a base that requires a merge queue, `gh pr merge` with green checks queues the PR: still OPEN."""
    later += [proven(isInMergeQueue=True), proven(isInMergeQueue=True), proven(state="MERGED")]
    assert waited(capsys, landing) == (
        0,
        [f"PR #7 merges at {HEAD}", f"PR #7: in the merge queue at {HEAD}", "PR #7 is merged"],
        [MERGE],
    )


def test_land_wait_ends_with_exit_1_when_the_pr_leaves_the_merge_queue_unmerged(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    later += [proven(isInMergeQueue=True), proven()]
    assert waited(capsys, landing) == (
        1,
        [f"PR #7 merges at {HEAD}", f"PR #7: in the merge queue at {HEAD}", OFF],
        [MERGE],
    )


def test_land_wait_ends_with_exit_3_when_a_pending_check_turns_red(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    landing.update(auto=False, pull=proven("IN_PROGRESS"))
    later += [proven("FAILURE")]
    assert waited(capsys, landing) == (
        approvals.WAITING,
        [
            "PR #7: `check` is IN_PROGRESS on the head commit",
            "PR #7: `check` is FAILURE on the head commit",
        ],
        [],
    )


def test_land_wait_asks_for_the_owners_label_only_once_ci_has_passed_the_head(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"] = proven("IN_PROGRESS", files=(".github/ci.yml",))
    later += [proven("SUCCESS", files=(".github/ci.yml",))]
    assert waited(capsys, landing) == (
        approvals.WAITING,
        ["PR #7: `check` is IN_PROGRESS on the head commit", GITHUB, GITHUB],
        [],
    )


def test_land_wait_turns_on_auto_merge_and_ends_once_github_merges(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"] = proven("IN_PROGRESS")
    on = {"enabledAt": "2026-10-01T12:00:00Z"}
    later += [
        proven("IN_PROGRESS", autoMergeRequest=on),
        proven("SUCCESS", isInMergeQueue=True),  # a merge queue takes it over from auto-merge
        proven("SUCCESS", state="MERGED"),
    ]
    assert waited(capsys, landing) == (
        0,
        [
            f"PR #7: auto-merge on at {HEAD}, once check pass",
            f"PR #7: auto-merge is on at {HEAD}",
            f"PR #7: in the merge queue at {HEAD}",
            "PR #7 is merged",
        ],
        [(*MERGE, "--auto")],
    )


OFF = "PR #7: auto-merge was turned off, or the PR left the merge queue, without a merge"


def test_land_wait_says_auto_merge_was_turned_off_without_a_merge(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"] = proven("IN_PROGRESS")
    later += [proven("IN_PROGRESS")]
    assert waited(capsys, landing) == (
        1,
        [
            f"PR #7: auto-merge on at {HEAD}, once check pass",
            OFF,
        ],
        [(*MERGE, "--auto")],
    )


def test_land_wait_ends_with_exit_3_on_a_red_check_under_auto_merge_already_on(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    on = {"enabledAt": "2026-10-01T12:00:00Z"}
    landing["pull"] = proven("IN_PROGRESS", autoMergeRequest=on)
    later += [proven("FAILURE", autoMergeRequest=on)]
    assert waited(capsys, landing) == (
        approvals.WAITING,
        [f"PR #7: auto-merge is on at {HEAD}", "PR #7: `check` is FAILURE on the head commit"],
        [],
    )


@pytest.mark.parametrize(
    ("loop", "files", "hold"),
    [
        (GITHUB_RULE, (".github/ci.yml",), GITHUB),
        (
            GITHUB_RULE + "\nCI: none\n",
            ("app.py",),
            (
                "PR #7: the project has no CI (loop.md `CI: none`), and no local check passed on the head"
                " (approvals.py local-ci)"
            ),
        ),
    ],
)
def test_land_wait_ends_on_an_owner_or_local_ci_hold_under_auto_merge_already_on(
    landing: dict[str, Any],
    later: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    loop: str,
    files: tuple[str, ...],
    hold: str,
) -> None:
    """GitHub's auto-merge supplies neither the owner's label nor a local-ci record: the hold ends the wait."""
    Path("docs/agents/loop.md").write_text(loop)
    on = {"enabledAt": "2026-10-01T12:00:00Z"}
    landing["pull"] = proven("SUCCESS", files=files, autoMergeRequest=on)
    assert waited(capsys, landing) == (approvals.WAITING, [hold], [])


def test_land_wait_reruns_a_red_approvals_run_once(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    approvals_red(landing)
    later += [landing["pull"]]
    code, lines, calls = waited(capsys, landing)
    assert (code, calls) == (
        approvals.WAITING,
        [("run", "view", "12345"), ("run", "rerun", "12345"), ("run", "view", "12345")],
    )
    assert lines[-1] == (
        "PR #7: every proof holds but `loop:approvals` is FAILURE on the head commit, again after land --wait reran"
        " run 12345: read its log"
    )


def test_land_wait_stops_at_its_ceiling_naming_what_it_waits_for(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    landing.update(auto=False, pull=proven("QUEUED"))
    assert waited(capsys, landing) == (
        approvals.WAITING,
        [
            "PR #7: `check` is QUEUED on the head commit",
            "PR #7: land --wait stopped after 2 hours, still waiting for CI on the head",
        ],
        [],
    )


def test_land_wait_ends_with_exit_3_on_more_checks_than_the_gate_reads(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    """CI never clears a query's one page: the refusal ends the wait instead of polling it to the ceiling."""
    landing.update(auto=False, rulesets=[], pull=proven(None))
    rollup = landing["pull"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]
    rollup["nodes"] = [
        {
            "__typename": "CheckRun",
            "name": f"check-{n}",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        }
        for n in range(100)
    ]
    rollup["totalCount"] = 101
    assert waited(capsys, landing) == (
        approvals.WAITING,
        ["PR #7 has more than 100 CI checks: the gate reads one page"],
        [],
    )


UNKNOWN = "PR #7: GitHub hasn't computed whether it can merge yet: run land again"


def test_land_neither_readies_nor_merges_before_github_computes_the_merge_state(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"] = proven(mergeStateStatus="UNKNOWN")
    assert landed(capsys, landing) == (approvals.WAITING, [UNKNOWN], [])


def test_land_wait_rereads_an_unknown_merge_state_before_marking_a_draft_ready(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    """A draft whose merge state resolves to a conflict is refused while still a draft."""
    landing["pull"] = proven("SKIPPED", isDraft=True, mergeStateStatus="UNKNOWN")
    later += [proven("SKIPPED", isDraft=True, mergeStateStatus="DIRTY")]
    code, lines, calls = waited(capsys, landing)
    assert (code, lines[0], calls) == (1, UNKNOWN, [])
    assert lines[1].startswith("PR #7 conflicts with main")


@pytest.mark.parametrize(
    ("status", "stale"), [("BEHIND", "is behind"), ("DIRTY", "conflicts with")]
)
@pytest.mark.parametrize("argv", [["land", "7"], ["land", "7", "--wait"]])
def test_land_refuses_a_head_behind_or_in_conflict_with_its_base_before_marking_it_ready(
    landing: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    status: str,
    stale: str,
    argv: list[str],
) -> None:
    """GitHub's refusal of a branch behind a base that requires it up to date reads `Required status check
    "qualify" is expected`; land names the cause first."""
    landing["pull"] = proven("SKIPPED", isDraft=True, mergeStateStatus=status)
    assert approvals.main(argv) == 1
    assert capsys.readouterr().out.splitlines() == [
        (
            f"PR #7 {stale} main: merge origin/main in, rerun the gates, get a verdict on the merge"
            " (lead.md step 8), then land again"
        )
    ]
    assert landing["calls"] == []


# --- land: a local signed squash, where loop.md says so ---

REPO = "https://github.com/kzarzycki/scratch-gate-revert"
SIGNED_LAND = "\nLand: local signed squash to main, allowed signers signers\n"


def sh(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def signing(landing: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """`landing` in a real checkout whose `origin` names the PR's repo and reaches a local bare repo: `main` and the
    PR's branch `feature` (also `refs/pull/7/head`) one commit ahead, an SSH signing key, and an allowed signers file
    `signers` holding it. The PR's head and verdict are the real commit; loop.md has the `Land:` line."""
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    sh("git", "init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git = lambda *args: sh("git", "-c", "commit.gpgsign=false", *args, cwd=tmp_path)
    git("init", "-q", "-b", "main")
    git("config", "user.name", "Lander")
    git("config", "user.email", "lander@example.com")
    git("remote", "add", "origin", REPO)
    git("config", f"url.{remote.as_uri()}.insteadOf", REPO)
    git("add", "docs")
    git("commit", "-qm", "base")
    git("push", "-q", "origin", "main")
    git("switch", "-qc", "feature")
    (tmp_path / "app.py").write_text("print('feature')\n")
    git("add", "app.py")
    git("commit", "-qm", "feature")
    git("push", "-q", "origin", "feature", "HEAD:refs/pull/7/head")
    git("switch", "-q", "main")
    key = tmp_path.parent / f"{tmp_path.name}-key"
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "lander", "-f", str(key), cwd=tmp_path)
    git("config", "gpg.format", "ssh")
    git("config", "user.signingkey", str(key))
    (tmp_path / "signers").write_text(f"lander@example.com {key.with_suffix('.pub').read_text()}")
    loop = tmp_path / "docs" / "agents" / "loop.md"
    loop.write_text(loop.read_text() + SIGNED_LAND)
    head = git("rev-parse", "feature")
    landing["pull"].update(
        headRefOid=head, reviews={"nodes": [verdict_on(head, "0 blocker, 0 major, 0 minor")]}
    )
    return {"git": git, "remote": remote, "base": git("rev-parse", "main"), "head": head}


def remote_ref(signing: dict[str, Any], ref: str) -> str:
    return sh("git", "rev-parse", ref, cwd=signing["remote"])


def test_land_with_the_line_squashes_signs_and_pushes_the_pr_branch_then_main(
    landing: dict[str, Any], signing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, calls = landed(capsys, landing)
    commit = remote_ref(signing, "main")
    assert (code, out, calls) == (
        0,
        [f"PR #7 landed in main as {commit}, signed by a key in signers"],
        [],  # never `gh pr merge`: GitHub's squash would carry GitHub's signature
    )
    git = signing["git"]
    assert (
        remote_ref(signing, "feature") == commit
    )  # GitHub marks the PR merged: its head is in main
    assert git("rev-parse", f"{commit}^") == signing["base"]  # one commit on main's old tip
    assert git("rev-parse", f"{commit}^{{tree}}") == git("rev-parse", f"{signing['head']}^{{tree}}")
    assert git("log", "-1", "--format=%s", commit) == "Feature (#7)"
    git("-c", "gpg.ssh.allowedSignersFile=signers", "verify-commit", commit)


def refused_untouched(
    landing: dict[str, Any], signing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> list[str]:
    code, out, calls = landed(capsys, landing)
    assert (code, calls) == (1, [])
    assert remote_ref(signing, "feature") == signing["head"]
    return out


def test_land_with_the_line_refuses_a_checkout_that_signs_nothing(
    landing: dict[str, Any], signing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    signing["git"]("config", "--unset", "user.signingkey")
    assert refused_untouched(landing, signing, capsys) == [
        "this checkout signs no commits with an SSH key: set `gpg.format ssh` and `user.signingkey`"
    ]
    assert remote_ref(signing, "main") == signing["base"]


def test_land_with_the_line_refuses_a_signature_the_allowed_signers_lack(
    landing: dict[str, Any],
    signing: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    other = tmp_path.parent / f"{tmp_path.name}-other"
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other), cwd=tmp_path)
    (tmp_path / "signers").write_text(f"lander@example.com {other.with_suffix('.pub').read_text()}")
    [line] = refused_untouched(landing, signing, capsys)
    assert line.startswith("PR #7: the squash is not signed by a key in signers: ")
    assert remote_ref(signing, "main") == signing["base"]


def test_land_with_the_line_refuses_a_pr_from_another_repository(
    landing: dict[str, Any], signing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"]["isCrossRepository"] = True
    assert refused_untouched(landing, signing, capsys) == [
        (
            "PR #7 comes from another repository: its branch isn't ours to push, push it to"
            " kzarzycki/scratch-gate-revert first"
        )
    ]


def test_land_with_the_line_refuses_a_pr_missing_the_base_head(
    landing: dict[str, Any], signing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    git = signing["git"]
    git("commit", "-q", "--allow-empty", "-m", "landed meanwhile")
    git("push", "-q", "origin", "main")
    tip = git("rev-parse", "main")
    assert refused_untouched(landing, signing, capsys) == [
        (
            f"PR #7 does not contain main's head {tip}: merge origin/main in, rerun the gates, get a verdict on the"
            " merge (lead.md step 8), then land again"
        )
    ]
    assert remote_ref(signing, "main") == tip


def test_land_with_the_line_moves_neither_branch_when_the_base_moves_during_the_push(
    landing: dict[str, Any],
    signing: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another PR lands between the squash and its push: the base keeps that commit, and the PR's branch its head."""
    git, real = signing["git"], approvals.git
    moved = []

    def landing_meanwhile(*args: str) -> str:
        if args[0] == "push" and not moved:
            tree = git("rev-parse", f"{signing['base']}^{{tree}}")
            moved.append(git("commit-tree", "-p", signing["base"], "-m", "another landing", tree))
            git("push", "-q", "origin", f"{moved[0]}:refs/heads/main")
        return real(*args)

    monkeypatch.setattr(approvals, "git", landing_meanwhile)
    [line] = refused_untouched(landing, signing, capsys)
    assert line.startswith(
        f"PR #7: main refused the squash, so feature is back at {signing['head']}: "
    )
    assert remote_ref(signing, "main") == moved[0]


def test_land_with_the_line_refuses_another_base_and_a_line_it_cannot_read(
    landing: dict[str, Any],
    signing: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    landing["pull"]["baseRefName"] = "release"
    assert refused_untouched(landing, signing, capsys) == [
        "PR #7 targets release, but loop.md lands signed squashes only to main"
    ]
    loop = tmp_path / "docs" / "agents" / "loop.md"
    loop.write_text(loop.read_text().replace(SIGNED_LAND, "\nLand: signed\n"))
    assert refused_untouched(landing, signing, capsys) == [
        (
            "loop.md has a `Land:` line this can't read: write it"
            " `Land: local signed squash to <branch>, allowed signers <path>`"
        )
    ]


def test_land_with_the_line_waits_for_pending_checks_without_auto_merge(
    landing: dict[str, Any], signing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """GitHub's auto-merge would squash with GitHub's key, so the signed landing waits for the checks itself."""
    landing["pull"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"][
        0
    ].update(status="IN_PROGRESS", conclusion=None)
    code, _, calls = landed(capsys, landing)
    assert (code, calls) == (3, [])
    assert remote_ref(signing, "main") == signing["base"]


# --- opt-out: a person keeps their PR out of the loop ---

OPTED = LOOP + "\nOpt-out: allowed\n"
OUTSIDE = (
    "PR #7 is outside the loop (loop.md `Opt-out: allowed`, no verifier review, spec approval,"
    " revert or bot exemption): its author merges it"
)


def gate(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, list[str]]:
    code = approvals.main(list(argv))
    return code, capsys.readouterr().out.splitlines()


@pytest.mark.parametrize(
    ("line", "allowed"),
    [
        ("Opt-out: allowed", True),
        ("- `Opt-out: allowed` (personal instructions say so)", True),
        ("Opt-out: allowed for nobody", False),
        ("Opt-out: no", False),
    ],
)
def test_only_a_bare_opt_out_line_allows_it(line: str, allowed: bool) -> None:
    assert approvals.opted_out(f"## Owner\n\n{line}\n") is allowed


def test_a_pr_with_no_loop_trail_is_outside_the_loop_where_opt_out_is_allowed(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    Path("docs/agents/loop.md").write_text(OPTED)
    mine = landing["pull"]
    mine["reviews"]["nodes"] = []
    mine["closingIssuesReferences"]["nodes"] = [specced(1, "kind:bug")]
    assert gate(capsys, "check", "merge", "7") == (0, [OUTSIDE])
    # land never merges it, nor turns auto-merge on: the gate before it is the loop's
    assert landed(capsys, landing) == (1, [OUTSIDE], [])
    # risk rules hold no PR outside the loop: the project accepted that with the line
    mine["labels"]["nodes"].append({"name": "risk:high"})
    assert gate(capsys, "check", "merge", "7") == (0, [OUTSIDE])
    # without the line, the same PR fails the gate as before
    Path("docs/agents/loop.md").write_text(LOOP)
    code, lines = gate(capsys, "check", "merge", "7")
    assert code == 1 and "PR #7: no verifier review posted (approvals.py verdict)" in lines


@pytest.mark.parametrize("trail", ["review", "spec-record", "approved-spec", "revert"])
def test_any_loop_trail_keeps_the_pr_in_the_loop(landing: dict[str, Any], trail: str) -> None:
    mine = landing["pull"]
    mine["reviews"]["nodes"] = [VERDICT] if trail == "review" else []
    linked = specced(1, "kind:bug")
    if trail == "spec-record":
        linked = issue(1, "kind:bug", comments=(record("spec", "loop", spec="as written x"),))
    if trail == "approved-spec":
        linked = specced(1, "kind:bug", "approved:spec")
    if trail == "revert":
        mine["body"] = "Reverts #3\n\n## Evidence\n\nwrong\n"
    mine["closingIssuesReferences"]["nodes"] = [linked]
    assert approvals.outside(mine, OPTED) is None
    assert approvals.outside({**mine, "reviews": {"nodes": []}, "body": ""}, LOOP) is None


def test_an_exempt_bot_pr_keeps_its_trail() -> None:
    pr = {**pull(files=("uv.lock",)), "author": {"__typename": "Bot", "login": "dependabot"}}
    pr["authored"] = {"nodes": [authored("dependabot[bot]")]}
    assert approvals.outside(pr, BOTS + "Opt-out: allowed\n") is None
    assert approvals.outside(pr, OPTED) is not None  # no `bot:` line: a person's PR like any other


def test_a_policy_covered_spec_is_no_trail(landing: dict[str, Any]) -> None:
    mine = landing["pull"]
    mine["reviews"]["nodes"] = []
    mine["closingIssuesReferences"]["nodes"] = [
        specced(1, "kind:bug")
    ]  # `spec: auto unless risk` covers a bug
    assert approvals.outside(mine, OPTED) == OUTSIDE


# --- a repo without the loop's files ---


def test_without_loop_md_an_issue_needs_only_approved_spec_and_no_needs_owner(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    for name in ("issue-tracker.md", "loop.md"):
        (tmp_path / "docs" / "agents" / name).unlink()
    bare = issue(1, "approved:spec")  # no category, component, size or approval record
    landing["pull"]["closingIssuesReferences"]["nodes"] = [bare]
    landing["pull"]["files"]["nodes"] = [{"path": ".github/ci.yml"}]
    assert landed(capsys, landing) == (0, [f"PR #7 merges at {HEAD}"], [MERGE])
    landing["calls"].clear()
    landing["pull"]["closingIssuesReferences"]["nodes"] = [
        issue(1, "approved:spec", "needs-owner"),
        issue(2, "size:XL"),
    ]
    assert landed(capsys, landing) == (
        1,
        ["#1 waits for the owner (needs-owner)", "#2 lacks the `approved:spec` label"],
        [],
    )


def test_without_the_tracker_file_no_label_shape_is_checked(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "docs" / "agents" / "issue-tracker.md").unlink()
    landing["pull"]["closingIssuesReferences"]["nodes"] = [approved(1)]  # no category or component
    assert approvals.main(["check", "build", "7"]) == 0
    assert capsys.readouterr().out == ""


def test_a_run_from_a_subdirectory_reads_the_checkouts_loop_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    committed(repo)
    agents = repo / "docs" / "agents"
    agents.mkdir(parents=True)
    (agents / "issue-tracker.md").write_text(TRACKER)
    (agents / "loop.md").write_text("## Practice\n\n- Plan: writing-plans\n")
    (repo / "src").mkdir()
    pr = pull()
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.setattr(approvals, "toplevel", TOPLEVEL)
    monkeypatch.chdir(repo / "src")
    assert (approvals.main(["check", "build", "7"]), capsys.readouterr().out) == (
        1,
        "#1 has no `## Plan` comment, and one is due\n",
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


def test_run_outside_a_git_checkout_fails_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(approvals, "toplevel", TOPLEVEL)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.chdir(tmp_path)
    assert (approvals.main(["check", "build", "1"]), capsys.readouterr().out) == (
        1,
        "not in a git checkout: run from the repo's checkout\n",
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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:billing", "kind:research")]
    monkeypatch.setattr(approvals, "pull_request", lambda _pr: pr)
    monkeypatch.chdir(tmp_path)
    assert (approvals.main(["check", "build", "7"]), capsys.readouterr().out) == (0, "")


# --- local-ci: the local check, run on the PR head ---


@pytest.fixture
def checkout(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, Any]:
    """A checkout at the PR head and clean, its git common dir under tmp_path; a test changes it, or what the check
    does to it. `runs` counts the checks run."""
    state: dict[str, Any] = {"head": HEAD, "status": "", "exit": 0, "after": None, "runs": 0}
    state["common"] = tmp_path / "common.git"
    state["loop"] = LOOP

    def git(*args: str) -> str:
        if args == ("rev-parse", "--path-format=absolute", "--git-common-dir"):
            return f"{state['common']}\n"
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
        state["runs"] += 1
        if state["after"]:
            state["status"] = state["after"]
        return subprocess.CompletedProcess(command, state["exit"])

    monkeypatch.setattr(approvals, "pull_request", lambda _n: pull())
    monkeypatch.setattr(approvals, "git", git)
    monkeypatch.setattr(approvals.subprocess, "run", run)
    monkeypatch.setattr(approvals, "one_repo", lambda: None)  # the faked run serves the check alone
    monkeypatch.setattr(approvals, "project", lambda: (None, state["loop"]))
    return state


def test_a_passing_check_on_the_clean_head_is_recorded(
    github: list[tuple[Any, ...]], checkout: dict[str, Any]
) -> None:
    assert approvals.main(["local-ci", "7"]) == 0
    assert github == [
        (
            "comment",
            7,
            f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check:all\nEnv: default\n",
        )
    ]
    record = json.loads(
        (checkout["common"] / "approvals" / "local-ci" / f"{HEAD}.json").read_text()
    )
    assert {k: record[k] for k in ("head", "command", "exit")} == {
        "head": HEAD,
        "command": "mise run check:all",
        "exit": 0,
    }
    assert record["time"] and record["host"]


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
    assert not (checkout["common"] / "approvals").exists()


@pytest.mark.parametrize(
    "change", [{"status": " M app.py\n"}, {"exit": 2}, {"after": " M uv.lock\n"}]
)
def test_record_writes_only_a_passing_check_on_a_clean_unchanged_tree(
    github: list[tuple[Any, ...]], checkout: dict[str, Any], change: dict[str, Any]
) -> None:
    checkout.update(change)
    assert approvals.main(["local-ci", "--record"]) == 1
    assert not (checkout["common"] / "approvals").exists()
    checkout.update({"status": "", "exit": 0, "after": None})
    assert approvals.main(["local-ci", "--record"]) == 0
    assert (checkout["common"] / "approvals" / "local-ci" / f"{HEAD}.json").exists()
    assert github == []  # no PR yet: nothing is posted


def test_a_recorded_pass_on_the_head_is_posted_without_running_again(
    github: list[tuple[Any, ...]], checkout: dict[str, Any]
) -> None:
    assert approvals.main(["local-ci", "--record"]) == 0
    record = json.loads(
        (checkout["common"] / "approvals" / "local-ci" / f"{HEAD}.json").read_text()
    )
    checkout["head"] = "c" * 40  # the checkout moved on: the record still proves the PR's head
    assert approvals.main(["local-ci", "7"]) == 0
    assert checkout["runs"] == 1
    assert github == [
        (
            "comment",
            7,
            (
                f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check:all\nEnv: default\n"
                f"From the recorded run at {record['time']} on {record['host']}, not run again.\n"
            ),
        )
    ]
    posted = [body for kind, _pr, body in github if kind == "comment"]
    merged = pull(reviews=(VERDICT,), comments=tuple(posted), labels=OWNED, checks=())
    assert merge(merged, [approved(1, "area:web")], LOOP + "\nCI: none\n") == []


@pytest.mark.parametrize(
    ("file", "record"),
    [
        ("c" * 40, {"head": "c" * 40, "command": "mise run check:all", "exit": 0}),
        (HEAD, {"head": HEAD, "command": "mise run check", "exit": 0}),
        (HEAD, {"head": HEAD, "command": "mise run check:all", "exit": 2}),
        (HEAD, {"head": "c" * 40, "command": "mise run check:all", "exit": 0}),
    ],
    ids=["another head", "another command", "a failed run", "a record naming another head"],
)
def test_a_record_for_another_head_or_command_or_a_failed_run_runs_the_check(
    github: list[tuple[Any, ...]], checkout: dict[str, Any], file: str, record: dict[str, Any]
) -> None:
    where = checkout["common"] / "approvals" / "local-ci"
    where.mkdir(parents=True)
    (where / f"{file}.json").write_text(json.dumps({**record, "time": "t", "host": "h"}))
    assert approvals.main(["local-ci", "7"]) == 0
    assert checkout["runs"] == 1
    assert github == [
        (
            "comment",
            7,
            f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check:all\nEnv: default\n",
        )
    ]


ENV_LOOP = LOOP + "\nLocal CI env: GATE_UI_TESTS GATE_SCOPE\n"


def recorded_pass(checkout: dict[str, Any]) -> dict[str, Any]:
    return json.loads((checkout["common"] / "approvals" / "local-ci" / f"{HEAD}.json").read_text())


def test_a_pass_recorded_under_another_env_runs_the_check_again(
    github: list[tuple[Any, ...]], checkout: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout["loop"] = ENV_LOOP
    monkeypatch.delenv("GATE_SCOPE", raising=False)
    monkeypatch.setenv("GATE_UI_TESTS", "0")
    assert approvals.main(["local-ci", "--record"]) == 0
    assert recorded_pass(checkout)["env"] == {"GATE_SCOPE": None, "GATE_UI_TESTS": "0"}
    monkeypatch.delenv("GATE_UI_TESTS")  # unset is the default tier, not the same as 0
    assert approvals.main(["local-ci", "7"]) == 0
    assert checkout["runs"] == 2
    assert github == [
        (
            "comment",
            7,
            f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check:all\nEnv: default\n",
        )
    ]
    assert recorded_pass(checkout)["env"] == {"GATE_SCOPE": None, "GATE_UI_TESTS": None}


def test_a_pass_recorded_under_the_same_env_is_reused_and_names_it(
    github: list[tuple[Any, ...]], checkout: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout["loop"] = ENV_LOOP
    monkeypatch.setenv("GATE_UI_TESTS", "0")
    monkeypatch.setenv("GATE_SCOPE", "changed")
    assert approvals.main(["local-ci", "--record"]) == 0
    record = recorded_pass(checkout)
    assert approvals.main(["local-ci", "7"]) == 0
    assert checkout["runs"] == 1
    assert github == [
        (
            "comment",
            7,
            (
                f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check:all\n"
                "Env: GATE_SCOPE=changed GATE_UI_TESTS=0\n"
                f"From the recorded run at {record['time']} on {record['host']}, not run again.\n"
            ),
        )
    ]


def test_a_record_without_env_runs_the_check_again(
    github: list[tuple[Any, ...]], checkout: dict[str, Any]
) -> None:
    where = checkout["common"] / "approvals" / "local-ci"
    where.mkdir(parents=True)
    old = {"head": HEAD, "command": "mise run check:all", "exit": 0, "time": "t", "host": "h"}
    (where / f"{HEAD}.json").write_text(json.dumps(old))  # as 0.23.1 wrote it
    assert approvals.main(["local-ci", "7"]) == 0
    assert checkout["runs"] == 1
    assert recorded_pass(checkout)["env"] == {}


@pytest.mark.parametrize(
    "drop",
    [{"time": None}, {"host": None}, {"time": 1}, {"env": []}],
    ids=["no time", "no host", "a number for time", "env not a dict"],
)
def test_an_incomplete_record_runs_the_check_again(
    github: list[tuple[Any, ...]], checkout: dict[str, Any], drop: dict[str, Any]
) -> None:
    where = checkout["common"] / "approvals" / "local-ci"
    where.mkdir(parents=True)
    full = {
        "head": HEAD,
        "command": "mise run check:all",
        "exit": 0,
        "env": {},
        "time": "t",
        "host": "h",
    }
    record = {k: v for k, v in {**full, **drop}.items() if v is not None}
    (where / f"{HEAD}.json").write_text(json.dumps(record))
    assert approvals.main(["local-ci", "7"]) == 0
    assert checkout["runs"] == 1
    assert github == [
        (
            "comment",
            7,
            f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check:all\nEnv: default\n",
        )
    ]


@pytest.mark.parametrize("line", ["Local CI env:", "Local CI env: GATE-UI"])
def test_an_unreadable_local_ci_env_line_is_refused(
    github: list[tuple[Any, ...]],
    checkout: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    line: str,
) -> None:
    checkout["loop"] = LOOP + f"\n{line}\n"
    assert approvals.main(["local-ci", "7"]) == 1
    assert (checkout["runs"], github) == (0, [])
    assert "Local CI env" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["local-ci"], ["local-ci", "7", "--record"]])
def test_local_ci_takes_a_pr_or_record(
    github: list[tuple[Any, ...]], checkout: dict[str, Any], argv: list[str]
) -> None:
    assert approvals.main(argv) == 1
    assert (checkout["runs"], github) == (0, [])


def test_a_local_ci_record_is_the_merge_proof_without_ci(
    github: list[tuple[Any, ...]], checkout: dict[str, Any]
) -> None:
    assert approvals.main(["local-ci", "7"]) == 0
    posted = [body for kind, _pr, body in github if kind == "comment"]
    merged = pull(reviews=(VERDICT,), comments=tuple(posted), labels=OWNED, checks=())
    assert merge(merged, [approved(1, "area:web")], LOOP + "\nCI: none\n") == []


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


def test_a_record_made_in_one_worktree_is_reused_from_another(
    github: list[tuple[Any, ...]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    head = committed(repo)
    git_in(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "tree"), head)
    monkeypatch.setattr(approvals, "LOCAL_CI", ["true"])
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    monkeypatch.chdir(tmp_path / "tree")
    assert approvals.main(["local-ci", "--record"]) == 0
    assert git_in(repo, "status", "--porcelain", "--untracked-files=all") == ""  # nothing to commit
    monkeypatch.chdir(repo)
    assert approvals.reusable(head)["head"] == head
    assert approvals.reusable("c" * 40) is None


# --- the owner's policy: specs approved and merges landed without an agent's approval ---

POLICY = "## Approvals\n\n- spec: auto unless risk\n- merge: auto unless risk\n- risk: path `billing/**`\n"
EDITED = "2026-10-02T14:35:27Z"


def epic(*labels: str, by: str = "owner", **fields: Any) -> dict[str, Any]:
    """An epic as an issue's GraphQL `parent`, with `by`'s spec record of its first version."""
    found = issue(9, "kind:enhancement", *labels, comments=(record("spec", by, spec=AS_WRITTEN),))
    return {**found, **fields}


def story(
    parent: dict[str, Any], author: str | None = "worker", body: str = "the spec"
) -> dict[str, Any]:
    """A native sub-issue of `parent`, opened by `author`, with no approval of its own."""
    found = issue(1, "kind:enhancement", "area:web", "size:S", body=body)
    return {**found, "parent": parent, "author": {"login": author} if author else None}


@pytest.fixture
def writers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`worker` can write to the repo and nobody else can; the logins asked about."""
    asked: list[str] = []

    def writer(login: str) -> bool:
        asked.append(login)
        return login == "worker"

    monkeypatch.setattr(approvals, "writer", writer)
    return asked


@pytest.mark.parametrize(
    ("spec", "covered"),
    [
        (issue(1, "kind:bug"), True),
        (
            issue(
                1, "kind:enhancement", body="The rate.\n\nFound while #12 reviewing the invoice.\n"
            ),
            True,
        ),
        (issue(1, "kind:enhancement", body="- Found while #12, a follow-up\n"), True),
        (issue(1, "kind:enhancement", body="An example: `Found while #12`\n"), False),
        (issue(1, "kind:enhancement", body="The template:\n\n```\nFound while #12\n```\n"), False),
        (issue(1, "kind:enhancement", body="`Found while #12` is the line.\n"), False),
        (issue(1, "kind:bug", "epic"), False),
        (issue(1, "kind:enhancement", body="It was found while #12 ran.\n"), False),
        (story(epic("approved:spec")), True),
        (story(epic("approved:spec"), author="drive-by"), False),
        (story(epic("approved:spec"), author=None), False),
        (story(epic()), False),
        (story(epic("approved:spec", by="coordinator")), False),
        (story(epic("approved:spec", lastEditedAt=EDITED)), False),
        (issue(1, "kind:enhancement", "epic"), False),
    ],
    ids=[
        "bug",
        "follow-up",
        "follow-up-in-a-list",
        "quoted-follow-up",
        "fenced-follow-up",
        "line-start-quoted-follow-up",
        "bug-epic",
        "mid-line-follow-up",
        "writers-story",
        "non-writers-story",
        "ghost-authors-story",
        "story-of-an-epic-without-approved-spec",
        "story-of-an-epic-only-an-agent-approved",
        "story-of-an-epic-edited-since",
        "new-epic",
    ],
)
def test_spec_policy_covers_a_bug_a_follow_up_and_a_writers_story_of_an_approved_epic(
    writers: list[str], spec: dict[str, Any], covered: bool
) -> None:
    assert approvals.spec_policy(spec) is covered
    assert "parent {" in approvals.ISSUE and "author { login }" in approvals.ISSUE


def test_a_spec_policy_covers_needs_no_record_or_label_and_one_it_does_not_needs_the_owner(
    writers: list[str],
) -> None:
    bug, child, new_epic = (
        specced(1, "kind:bug"),
        story(epic("approved:spec")),
        specced(3, "kind:enhancement", "epic"),
    )
    assert approvals.proofs("build", pull(), [bug, child], POLICY) == []
    assert approvals.proofs("build", pull(), [new_epic], POLICY) == [
        "#3 has no `Approved: spec` record by the owner",
        "#3 lacks the `approved:spec` label",
    ]
    # without the policy line, a bug is the owner's to approve like any spec
    assert approvals.proofs(
        "build", pull(), [bug], "## Approvals\n\n- risk: path `billing/**`\n"
    ) == [
        "#1 has no `Approved: spec` record by the owner",
        "#1 lacks the `approved:spec` label",
    ]
    assert problems([specced(1, "kind:bug", "needs-owner")]) == [
        "#1 waits for the owner (needs-owner)"
    ]


AUTO = "## Approvals\n\n- spec: auto\n- risk: component `api`\n- risk: path `billing/**`\n"


def by(author: str, found: dict[str, Any]) -> dict[str, Any]:
    return {**found, "author": {"login": author}}


def test_spec_auto_is_a_policy_and_a_spec_condition_beside_it_a_risk_rule() -> None:
    assert approvals.spec_auto(AUTO) and not approvals.policy(AUTO, "spec")
    assert not approvals.spec_auto(POLICY)
    assert approvals.risk_rules(AUTO + "- spec: size:XL\n") == [
        "component `api`",
        "path `billing/**`",
        "size:XL",
    ]


def test_spec_auto_approves_every_spec_a_writer_opened_but_one_a_risk_rule_holds(
    writers: list[str],
) -> None:
    feature, new_epic = (
        by("worker", specced(1, "kind:enhancement")),
        by("worker", specced(3, "kind:enhancement", "epic")),
    )
    # risk:high holds the merge, not the spec
    marked = by("worker", specced(5, "kind:bug", "risk:high"))
    assert approvals.proofs("build", pull(), [feature, new_epic, marked], AUTO) == []
    held, outsider = (
        by("worker", specced(4, "kind:enhancement", "area:api")),
        by("drive-by", specced(6, "kind:bug")),
    )
    assert approvals.holds(pull(), [feature, held, outsider], AUTO) == [
        "#4: its spec is the owner's to approve under `spec: auto`, since it matches a risk rule (component `api`)",
        "#6: its spec is the owner's to approve under `spec: auto`, since its author @drive-by can't write to the repo",
    ]
    assert approvals.proofs("build", pull(), [held, outsider], AUTO) == [
        "#4 has no `Approved: spec` record by the owner",
        "#4 lacks the `approved:spec` label",
        "#6 has no `Approved: spec` record by the owner",
        "#6 lacks the `approved:spec` label",
    ]
    # the owner's approval lets a held spec build
    owned = by("worker", approved(4, "kind:enhancement", "area:api"))
    assert approvals.proofs("build", pull(), [owned], AUTO) == []


def test_under_spec_auto_a_file_the_spec_did_not_foresee_holds_the_spec(
    writers: list[str],
) -> None:
    feature = by("worker", specced(1, "kind:enhancement"))
    pushed = pull(files=("app.py", "billing/a.py"))
    assert approvals.holds(pushed, [feature], AUTO) == [
        "#1: its spec is the owner's to approve under `spec: auto`, since it matches a risk rule (path `billing/**`)"
    ]
    assert approvals.proofs("build", pushed, [feature], AUTO) == [
        "#1 has no `Approved: spec` record by the owner",
        "#1 lacks the `approved:spec` label",
    ]
    # a PR label counts too, and a rule the gate can't read holds
    assert approvals.holds(pull(labels=("area:api",)), [feature], AUTO)
    vague = AUTO + "- risk: anything touching money\n"
    assert approvals.holds(pull(), [feature], vague) == [
        "#1: its spec is the owner's to approve under `spec: auto`, since a risk rule the gate can't judge holds until a person does (anything touching money)"
    ]


def test_under_spec_auto_a_risk_rule_holds_no_merge_but_risk_high_and_the_cap_do(
    writers: list[str],
) -> None:
    owned = by("worker", approved(1, "kind:enhancement", "area:web"))
    done = pull(reviews=(VERDICT,), files=("billing/a.py",))
    assert merge(done, [owned], AUTO) == []
    assert approvals.risk(done, [owned], AUTO) is None
    marked = pull(reviews=(VERDICT,), files=("billing/a.py",), labels=("risk:high",))
    assert approvals.risk(marked, [owned], AUTO) == "`risk:high` is on PR #7"
    # the same PR beside `spec: auto unless risk` waits for the owner's merge label
    assert approvals.risk(done, [owned], POLICY) == "it matches a risk rule (path `billing/**`)"


def test_a_policy_line_is_no_condition_so_a_low_risk_pr_waits_for_nothing() -> None:
    done = pull(reviews=(VERDICT,), files=("app.py",))
    assert merge(done, [specced(1, "kind:bug")], POLICY) == []
    assert approvals.risk(done, [specced(1, "kind:bug")], POLICY) is None


def test_a_low_risk_agent_pr_lands_with_no_approval_record_and_no_label(
    landing: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    added: list[tuple[int, str, bool]],
) -> None:
    Path("docs/agents/loop.md").write_text(LOOP)
    follow_up = issue(
        1, "kind:enhancement", "area:web", "size:S", body="The fix.\n\nFound while #5 landing.\n"
    )
    landing["pull"]["closingIssuesReferences"]["nodes"] = [follow_up]
    assert approvals.main(["check", "build", "7"]) == 0
    assert landed(capsys, landing) == (0, [f"PR #7 merges at {HEAD}"], [MERGE])
    assert added == []


@pytest.mark.parametrize(
    ("labels", "issue_labels", "files", "why"),
    [
        (("risk:high",), (), ("app.py",), "`risk:high` is on PR #7"),
        ((), ("risk:high",), ("app.py",), "`risk:high` is on #1"),
        ((), (), ("billing/a.py",), "it matches a risk rule (path `billing/**`)"),
        (
            (),
            ("size:XL",),
            ("app.py",),
            "it matches a risk rule (size:L or larger, or component `api`)",
        ),
    ],
    ids=["label-on-the-pr", "label-on-its-issue", "risk-path", "legacy-spec-size-rule"],
)
def test_a_high_risk_merge_waits_for_the_owner_and_says_why(
    labels: tuple[str, ...], issue_labels: tuple[str, ...], files: tuple[str, ...], why: str
) -> None:
    loop = POLICY + "- spec: size:L or larger, or component `api`\n"
    found = approved(1, "area:web", *issue_labels)
    assert merge(pull(reviews=(VERDICT,), labels=labels, files=files), [found], loop) == [
        HELD + why
    ]
    signed = pull(reviews=(VERDICT,), labels=(*labels, *OWNED), files=files)
    assert merge(signed, [found], loop) == []


def test_land_adds_risk_high_when_it_infers_high_risk_and_holds_for_the_owner(
    landing: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    added: list[tuple[int, str, bool]],
) -> None:
    landing["pull"]["files"]["nodes"] = [{"path": ".github/ci.yml"}]
    assert landed(capsys, landing) == (approvals.WAITING, [GITHUB], [])
    assert added == [(7, "risk:high", True)]
    added.clear()
    landing["pull"]["labels"]["nodes"] = [{"name": "risk:high"}]
    landed(capsys, landing)
    assert added == []  # already on the PR
    signed = pull(reviews=(VERDICT,), files=(".github/ci.yml",), labels=("risk:high", *OWNED))
    signed["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    landing["pull"] = signed
    assert landed(capsys, landing) == (0, [f"PR #7 merges at {HEAD}"], [MERGE])


def test_check_merge_adds_risk_high_on_a_cap_hold_and_a_refused_label_is_reported_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    added: list[tuple[int, str, bool]],
) -> None:
    at_cap = verdict_on(
        OLD, "0 blocker, 1 major, 0 minor", satisfied="no", heading="Verifier (claude), pass 5"
    )
    pr = pull(
        reviews=(at_cap, verdict_on(HEAD, heading="Verifier (claude), pass 6")), files=("app.py",)
    )
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.chdir(PROJECT)
    capped_line = (
        HELD
        + "a verifier review at the cap (pass 5) or later was not satisfied or left a blocker or major open, so the owner decides"
    )
    assert approvals.main(["check", "merge", "7"]) == approvals.WAITING
    assert capsys.readouterr().out.splitlines() == [capped_line]
    assert added == [(7, "risk:high", True)]

    def refused(number: int, name: str, add: bool) -> None:
        raise subprocess.CalledProcessError(
            1, "gh", stderr="gh: Resource not accessible by integration (HTTP 403)\n"
        )

    monkeypatch.setattr(approvals, "label", refused)
    assert approvals.main(["check", "merge", "7"]) == approvals.WAITING
    assert capsys.readouterr().out.splitlines() == [
        capped_line,
        "PR #7: could not add `risk:high` (gh: Resource not accessible by integration (HTTP 403)): add it by hand",
    ]


@pytest.mark.parametrize(
    ("answer", "can"),
    [
        ("admin\n", True),
        ("maintain\n", True),
        ("write\n", True),
        ("read\n", False),
        ("none\n", False),
        (None, False),
    ],
)
def test_write_access_is_githubs_collaborator_permission(
    monkeypatch: pytest.MonkeyPatch, answer: str | None, can: bool
) -> None:
    asked: list[tuple[str, ...]] = []

    def gh(*args: str, data: str | None = None) -> str:
        asked.append(args)
        if answer is None:
            raise subprocess.CalledProcessError(1, "gh", stderr="gh: Not Found (HTTP 404)\n")
        return answer

    monkeypatch.setattr(approvals, "gh", gh)
    assert approvals.writer("worker") is can
    assert asked == [
        ("api", "repos/{owner}/{repo}/collaborators/worker/permission", "--jq", ".permission")
    ]


# --- assignees: who an issue belongs to ---


def held(
    found: dict[str, Any], *logins: str, events: tuple[dict[str, Any], ...] = ()
) -> dict[str, Any]:
    """`found` assigned to `logins`, with these timeline events."""
    return {
        **found,
        "assignees": {"nodes": [{"login": login} for login in logins]},
        "timelineItems": {"nodes": list(events)},
    }


def labelled(by: str, kind: str = "User", at: str = WRITTEN) -> dict[str, Any]:
    """`approved:spec` added by `by`."""
    return {
        "__typename": "LabeledEvent",
        "createdAt": at,
        "actor": {"__typename": kind, "login": by},
        "label": {"name": "approved:spec"},
    }


def assigned_event(login: str, at: str) -> dict[str, Any]:
    return {"__typename": "AssignedEvent", "createdAt": at, "assignee": {"login": login}}


def test_the_approver_is_who_added_approved_spec_else_the_account_running_the_loop() -> None:
    assert approvals.approver(held(approved(1), events=(labelled("ann"), labelled("bob")))) == "bob"
    assert (
        approvals.approver(held(approved(1), events=(labelled("github-actions", "Bot"),))) is None
    )
    assert approvals.approver(specced(1)) == "loop"  # a spec the policy approves: no label


@pytest.mark.parametrize(
    ("logins", "refused"),
    [((), False), (("ann",), False), (("bob",), True), (("ann", "bob"), True)],
)
def test_check_build_refuses_an_issue_assigned_to_anyone_but_its_approver(
    logins: tuple[str, ...], refused: bool
) -> None:
    found = held(approved(1, "kind:bug", "area:web"), *logins, events=(labelled("ann"),))
    line = (
        f"#1 is assigned to {', '.join('@' + login for login in logins)}, not to its approver @ann alone:"
        " someone else's issue is theirs, so the loop leaves it"
    )
    assert approvals.proofs("build", pull(), [found], LOOP) == ([line] if refused else [])
    assert approvals.proofs("merge", pull(reviews=(VERDICT,), labels=OWNED), [found], LOOP) == []


def test_being_assigned_is_no_go_ahead() -> None:
    claimed = held(specced(1, "kind:enhancement"), "loop")
    assert approvals.proofs("build", pull(), [claimed], LOOP) == [
        "#1 has no `Approved: spec` record by the owner",
        "#1 lacks the `approved:spec` label",
    ]


def test_building_assigns_the_approver_only_when_no_one_is_and_the_pr_follows(
    assigned: list[tuple[Any, ...]],
) -> None:
    free = held(approved(1), events=(labelled("ann"),))
    claimed = held(approved(2), "ann", events=(labelled("ann"),))
    assert approvals.claim(pull(), [free, claimed]) == []
    assert assigned == [
        (1, "Assigned: @ann\nBy: loop\nPR: #7\n"),
        (1, "ann", True),
        (7, "ann", True),
    ]
    assigned.clear()
    assert approvals.claim(held(pull(), "ann"), [claimed]) == []
    assert assigned == []


def test_check_build_claims_only_once_every_proof_holds(
    monkeypatch: pytest.MonkeyPatch,
    assigned: list[tuple[Any, ...]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(PROJECT)
    pr = pull()
    pr["closingIssuesReferences"]["nodes"] = [
        held(issue(1, "kind:enhancement", "area:web", "size:S"))
    ]
    monkeypatch.setattr(approvals, "pull_request", lambda _pr: pr)
    assert approvals.main(["check", "build", "7"]) == 1
    assert assigned == []
    pr["closingIssuesReferences"]["nodes"] = [
        held(specced(1, "kind:bug"))
    ]  # the policy approves a bug
    assert approvals.main(["check", "build", "7"]) == 0
    assert (1, "loop", True) in assigned
    capsys.readouterr()


def test_a_refused_assignment_is_reported_and_never_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(number: int, login: str, add: bool) -> None:
        raise subprocess.CalledProcessError(1, "gh", stderr="Validation Failed")

    monkeypatch.setattr(approvals, "assign", refuse)
    assert approvals.claim(pull(), [held(approved(1), events=(labelled("ann"),))]) == [
        "#1: could not assign @ann (Validation Failed)"
    ]


def test_a_refused_record_leaves_the_issue_unassigned_and_says_so(
    monkeypatch: pytest.MonkeyPatch, assigned: list[tuple[Any, ...]]
) -> None:
    def refuse(number: int, body: str) -> None:
        raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403: issue is locked")

    monkeypatch.setattr(approvals, "comment", refuse)
    assert approvals.claim(pull(), [held(approved(1), events=(labelled("ann"),))]) == [
        "#1: did not assign @ann: could not record the claim (HTTP 403: issue is locked)"
    ]
    assert assigned == []  # no assignment release would read as a person's


def test_parking_removes_only_the_assignee_the_loop_added(
    monkeypatch: pytest.MonkeyPatch,
    assigned: list[tuple[Any, ...]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    later = "2026-10-01T12:00:00Z"
    by_loop = note("Assigned: @ann\nBy: loop\nPR: #7\n", createdAt=PUSHED)
    found = {
        1: held(issue(1, comments=(by_loop,)), "ann", events=(assigned_event("ann", PUSHED),)),
        2: held(issue(2), "ann", events=(assigned_event("ann", PUSHED),)),  # the owner's own claim
        3: held(
            issue(3, comments=(by_loop,)),
            "ann",
            events=(assigned_event("ann", PUSHED), assigned_event("ann", later)),
        ),  # unassigned, then claimed again by the owner
        4: held(
            issue(4, comments=(by_loop,)), "ann", events=(assigned_event("ann", LABELED),)
        ),  # the loop's assignment, a moment after its record
    }
    monkeypatch.setattr(approvals, "issue_node", found.__getitem__)
    for number in found:
        assert approvals.main(["release", str(number)]) == 0
    assert assigned == [(1, "ann", False), (4, "ann", False)]
    assert capsys.readouterr().out.splitlines() == [
        "#1: removed @ann, whom the loop assigned",
        "#2: kept @ann, whose claim it is",
        "#3: kept @ann, whose claim it is",
        "#4: removed @ann, whom the loop assigned",
    ]


FORK, THEM = "https://github.com/me/fork.git", "git@github.com:them/fork"
POST_DEMO = SCRIPTS.parent.parent / "demo" / "scripts" / "post_demo.sh"


@pytest.mark.parametrize(
    ("remotes", "default", "refused"),
    [
        ({"origin": FORK}, False, False),
        ({"origin": FORK, "upstream": THEM}, False, True),
        ({"origin": FORK, "upstream": THEM}, True, False),
        ({"origin": FORK, "upstream": "https://github.com/them/fork.git/"}, False, True),
        ({"origin": FORK, "upstream": "https://GITHUB.COM/them/fork"}, False, True),
        ({"origin": FORK, "upstream": "ssh://git@github.com:22/them/fork.git"}, False, True),
        ({"origin": FORK, "upstream": "git@github.com:/them/fork.git"}, False, True),
        ({"origin": FORK, "upstream": "ssh://git@github.com//them/fork.git"}, False, True),
        ({"origin": FORK, "mirror": "https://gitlab.com/me/fork.git"}, False, False),
        ({"origin": FORK, "mirror": "https://gitlab.com/github.com/them/fork.git"}, False, False),
        ({"origin": FORK, "mirror": "https://notgithub.com/them/fork.git"}, False, False),
        ({"origin": FORK, "push": "git@github.com:Me/Fork.git"}, False, False),
    ],
)
def test_one_repo_refuses_several_github_remotes_without_a_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remotes: dict[str, str],
    default: bool,
    refused: bool,
) -> None:
    """gh reads `{owner}/{repo}` as `upstream`'s when several GitHub remotes have no default: approvals.py and
    post_demo.sh refuse, naming them, before any gh call."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, url in remotes.items():
        subprocess.run(["git", "-C", str(tmp_path), "remote", "add", name, url], check=True)
    if default:
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "remote.origin.gh-resolved", "base"], check=True
        )
    monkeypatch.chdir(tmp_path)
    if refused:
        with pytest.raises(approvals.Refused, match="me/fork, them/fork.*gh repo set-default"):
            approvals.one_repo()
    else:
        approvals.one_repo()
    # post_demo.sh: a gh that exits 77 on any call shows whether the guard let it through
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "gh").write_text("#!/bin/sh\nexit 77\n")
    (shim / "gh").chmod(0o755)
    (tmp_path / "v.mp4").write_bytes(b"x")
    shell = subprocess.run(
        ["bash", str(POST_DEMO), "x", "v.mp4"],
        capture_output=True,
        text=True,
        env={"PATH": f"{shim}:/usr/bin:/bin", "HOME": str(tmp_path)},
        check=False,
    )
    assert (shell.returncode, "me/fork them/fork" in shell.stderr) == (
        (1, True) if refused else (77, False)
    )


# --- the verifier judges risk (`risk: verifier`) ---


VERIFIED = POLICY.replace("- risk: path `billing/**`\n", "- risk: verifier\n")


def judging(risk: str | None, commit: str = HEAD, **fields: Any) -> dict[str, Any]:
    """A satisfied verifier review whose last line is `Risk: <risk>`, or none with None."""
    review = verdict_on(commit, **fields)
    return {**review, "body": review["body"] + (f"Risk: {risk}\n" if risk else "")}


@pytest.fixture
def gating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], list[tuple[int, str]]]:
    """`check merge` in a checkout with a `risk: verifier` loop.md: the PR it reads, and every comment it posts."""
    agents = tmp_path / "docs" / "agents"
    agents.mkdir(parents=True)
    (agents / "issue-tracker.md").write_text(TRACKER)
    (agents / "loop.md").write_text(VERIFIED)
    state: dict[str, Any] = {}
    comments: list[tuple[int, str]] = []
    monkeypatch.setattr(approvals, "pull_request", lambda _n: state["pull"])
    monkeypatch.setattr(approvals, "comment", lambda number, body: comments.append((number, body)))
    monkeypatch.chdir(tmp_path)
    return state, comments


def judged_pr(*reviews: dict[str, Any], **fields: Any) -> dict[str, Any]:
    pr = pull(reviews=reviews, files=("app.py",), **fields)
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:enhancement")]
    return pr


def test_risk_low_from_the_verifier_merges_without_the_owner(
    gating: tuple[dict[str, Any], list[tuple[int, str]]],
    capsys: pytest.CaptureFixture[str],
    added: list[tuple[int, str, bool]],
) -> None:
    state, comments = gating
    state["pull"] = judged_pr(judging("low — a flag on two test commands"))
    assert approvals.main(["check", "merge", "7"]) == 0
    assert capsys.readouterr().out == ""
    assert (added, comments) == ([], [])


@pytest.mark.parametrize(
    ("risk", "said"),
    [
        (
            "high — it narrows the test selection",
            "says `Risk: high — it narrows the test selection`",
        ),
        ("medium — unsure", "says `Risk: medium — unsure`"),
        (None, "has no `Risk:` line"),
    ],
    ids=["high", "another-word", "no-line"],
)
def test_risk_high_another_word_or_no_line_waits_for_the_owner_and_flags_the_pr(
    gating: tuple[dict[str, Any], list[tuple[int, str]]],
    capsys: pytest.CaptureFixture[str],
    added: list[tuple[int, str, bool]],
    risk: str | None,
    said: str,
) -> None:
    state, comments = gating
    state["pull"] = judged_pr(judging(risk))
    why = f"it matches a risk rule (verifier): the verifier's pass 1 on {HEAD[:7]} {said}"
    assert approvals.main(["check", "merge", "7"]) == approvals.WAITING
    assert capsys.readouterr().out.splitlines() == [HELD + why]
    assert added == [(7, "risk:high", True)]
    assert [number for number, _ in comments] == [7]
    assert comments[0][1].startswith(f"{approvals.FLAGGED}, since {why}.")
    signed = judged_pr(judging(risk), labels=("risk:high", *OWNED))
    assert merge(signed, signed["closingIssuesReferences"]["nodes"], VERIFIED) == []


def test_a_risk_low_on_an_older_head_or_by_a_stranger_does_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(approvals, "writer", lambda login: False)
    issues = [approved(1, "area:web", "kind:enhancement")]
    older = judged_pr(judging("low — fine", commit=OLD))
    assert (
        approvals.proofs("merge", older, issues, VERIFIED) != []
    )  # no verdict on the head lands nothing
    high = judging("high — a gate weakened")
    stranger = judging("low — fine", author="stranger", heading="Verifier (claude), pass 2")
    pr = judged_pr(high, stranger)
    assert merge(pr, issues, VERIFIED) == [
        HELD
        + f"it matches a risk rule (verifier): the verifier's pass 1 on {HEAD[:7]} says `Risk: high — a gate weakened`"
    ]
    # a mixed PR's two verifiers on one pass: both must say low
    other = judging("high — CI permissions", heading="Verifier (codex), pass 1")
    assert approvals.judged(judged_pr(judging("low — fine"), other)) == (
        f"the verifier's pass 1 on {HEAD[:7]} says `Risk: high — CI permissions`"
    )


def test_a_path_term_holds_whatever_the_verifier_says() -> None:
    loop = POLICY.replace("- risk: path `billing/**`\n", "- risk: verifier or path .github/**\n")
    pr = pull(reviews=(judging("low — a workflow comment"),), files=(".github/ci.yml",))
    issues = [approved(1, "area:web", "kind:enhancement")]
    assert merge(pr, issues, loop) == [
        HELD + "it matches a risk rule (verifier or path .github/**)"
    ]
    assert merge({**pr, "files": {"nodes": [{"path": "app.py"}]}}, issues, loop) == []


@pytest.mark.parametrize("spec", ["", "- spec: auto\n"], ids=["merge", "spec-auto"])
@pytest.mark.parametrize(
    "condition", ["path docs/verifier.md", "path `verifier/**`", "component verifier"]
)
def test_the_word_verifier_in_a_path_or_label_is_no_verifier_term(
    spec: str, condition: str
) -> None:
    """A rule without the `verifier` term holds as it did before it: the verifier's `Risk:` line, high or missing,
    holds nothing."""
    loop = f"## Approvals\n\n{spec}- risk: {condition}\n"
    issues = [approved(1, "area:web", "kind:enhancement")]
    for review in (judging("high — a gate changed"), judging(None)):
        assert approvals.risk(pull(reviews=(review,), files=("app.py",)), issues, loop) is None


def test_under_spec_auto_the_verifier_term_holds_the_merge_not_the_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(approvals, "writer", lambda login: True)
    loop = "## Approvals\n\n- spec: auto\n- risk: verifier or path `billing/**`\n"
    owned = by("worker", specced(5, "kind:enhancement"))
    pr = pull(reviews=(judging("low — fine"),), files=("app.py",))
    assert approvals.proofs("build", pr, [owned], loop) == []
    assert approvals.risk(pr, [owned], loop) is None
    high = pull(reviews=(judging("high — surprises users"),), files=("app.py",))
    assert approvals.proofs("build", high, [owned], loop) == []
    assert approvals.risk(high, [owned], loop) == (
        "it matches a risk rule's `verifier` term: the verifier's pass 1 on"
        f" {HEAD[:7]} says `Risk: high — surprises users`"
    )


def test_the_gates_risk_high_comes_off_when_a_later_pass_judges_it_low_and_a_raise_stays(
    gating: tuple[dict[str, Any], list[tuple[int, str]]],
    capsys: pytest.CaptureFixture[str],
    added: list[tuple[int, str, bool]],
) -> None:
    state, _ = gating
    flagged = note(f"{approvals.FLAGGED}, since …", createdAt="2026-10-01T11:00:01Z")
    rejudged = judging("low — the lead's reason holds", heading="Verifier (claude), pass 2")
    state["pull"] = judged_pr(judging("high — x"), rejudged, labels=("risk:high",))
    state["pull"]["comments"]["nodes"].append(flagged)
    assert approvals.main(["check", "merge", "7"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "PR #7: removed the `risk:high` the gate added, since the verifier now judges the risk low"
    ]
    assert added == [(7, "risk:high", False)]
    added.clear()
    # the lead raised it again after the gate's comment: only the owner lowers it
    state["pull"] = judged_pr(judging("high — x"), rejudged, labels=("risk:high",))
    state["pull"]["comments"]["nodes"].append({**flagged, "createdAt": "2026-10-01T10:30:00Z"})
    assert approvals.main(["check", "merge", "7"]) == approvals.WAITING
    assert added == []
    # a person's label with no gate comment stays too
    state["pull"] = judged_pr(rejudged, labels=("risk:high",))
    assert approvals.main(["check", "merge", "7"]) == approvals.WAITING
    assert added == []


def test_a_report_without_a_risk_line_posts_nothing(
    reviewing: list[tuple[Any, ...]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.md"
    report.write_text(REPORT.replace("Risk: low — a test fixture\n", ""))
    assert approvals.main(["verdict", "7", str(report)]) == 1
    assert capsys.readouterr().out == (
        f"{report} has no `Risk: low|high — <reason>` line: the report is unfinished\n"
    )
    assert [call for call in reviewing if call[0] == "review"] == []


# --- a batching merge queue: check queue, batch, and the batch proof check merge accepts ---


@pytest.fixture
def batched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A bare `origin` whose `main` took a merge queue's batch: the PR's head `feature` merged cleanly onto a `main`
    that moved since it branched (`merge`), then another story merged on top (`batch`). Beside it, a merge of the head
    that adds a file no parent has (`evil`), a clean merge of another commit (`other`), and a commit off the batch
    (`stray`). The test runs in a clone made before the batch was pushed, so check merge must fetch it."""
    origin, work, checker = (tmp_path / name for name in ("origin.git", "work", "checker"))
    sh("git", "init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    git = lambda *args: sh(
        "git",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "user.name=Queue",
        "-c",
        "user.email=q@example.com",
        *args,
        cwd=work,
    )
    sh("git", "clone", "-q", str(origin), str(work), cwd=tmp_path)

    def commit(name: str) -> None:
        (work / name).write_text(f"{name}\n")
        git("add", name)
        git("commit", "-qm", name)

    commit("base.txt")
    git("push", "-q", "origin", "HEAD:main")
    sh("git", "clone", "-q", str(origin), str(checker), cwd=tmp_path)
    git("switch", "-qc", "feature")
    commit("feature.txt")
    head = git("rev-parse", "HEAD")
    git("switch", "-qc", "story", "main")
    commit("story.txt")
    git("switch", "-q", "main")
    commit("moved.txt")
    git("merge", "-q", "--no-ff", "-m", "Merge feature", "feature")
    merge = git("rev-parse", "HEAD")
    git("merge", "-q", "--no-ff", "-m", "Merge story", "story")
    batch = git("rev-parse", "HEAD")
    git("push", "-q", "origin", "HEAD:main")
    git("switch", "-q", "--detach", f"{merge}^1")
    git("merge", "-q", "--no-ff", "--no-commit", "feature")
    (work / "extra.txt").write_text("not in either parent\n")
    git("add", "extra.txt")
    git("commit", "-qm", "Merge feature, and more")
    evil = git("rev-parse", "HEAD")
    git("switch", "-q", "--detach", f"{merge}^1")
    git("merge", "-q", "--no-ff", "-m", "Merge story", "story")
    other = git("rev-parse", "HEAD")
    commit("stray.txt")
    stray = git("rev-parse", "HEAD")
    git("push", "-q", "origin", f"{evil}:refs/heads/evil", f"{stray}:refs/heads/stray")
    monkeypatch.chdir(checker)
    return {
        "head": head,
        "merge": merge,
        "batch": batch,
        "evil": evil,
        "other": other,
        "stray": stray,
    }


def batch_note(head: str, merge: str, batch: str, exit: int = 0) -> str:
    return f"{approvals.BATCHED}\nHead: {head}\nMerge: {merge}\nBatch: {batch}\nExit: {exit}\nLog: /tmp/gate.log\n"


NO_LOCAL_CHECK = "PR #7: the project has no CI (loop.md `CI: none`), and no local check passed on the head (approvals.py local-ci)"


def queued_merge(head: str, *comments: str) -> list[str]:
    pr = pull(reviews=(verdict_on(head),), comments=comments, checks=())
    pr["headRefOid"] = head
    return merge(pr, [approved(1, "area:web")], LOOP + "\nCI: none\n")


def test_a_green_batch_that_merged_the_head_cleanly_is_its_merge_proof(
    batched: dict[str, str],
) -> None:
    head, merged, batch = batched["head"], batched["merge"], batched["batch"]
    assert queued_merge(head, batch_note(head, merged, batch)) == []
    # the batch's tip is the merge itself when the PR merged last
    assert queued_merge(head, batch_note(head, merged, merged)) == []


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"exit": 1}, "the merge queue's gate on batch {batch} exited 1"),
        ({"merge": "other"}, "merge {other} does not merge the head {head} as its second parent"),
        (
            {"merge": "evil"},
            "merge {evil} is not the clean merge of its parents: the queue resolved or added something",
        ),
        ({"batch": "stray"}, "batch {stray} does not contain merge {merge}"),
        ({"merge": "f" * 40}, "merge {fff} is not a commit origin has"),
    ],
)
def test_a_red_or_unproven_batch_is_no_merge_proof(
    batched: dict[str, str], change: dict[str, Any], said: str
) -> None:
    head = batched["head"]
    fields = {"merge": batched["merge"], "batch": batched["batch"], "exit": 0}
    fields.update(
        {key: batched.get(value, value) for key, value in change.items() if key != "exit"}
    )
    fields["exit"] = change.get("exit", 0)
    names = {**batched, "fff": "f" * 40}
    assert queued_merge(
        head, batch_note(head, fields["merge"], fields["batch"], fields["exit"])
    ) == [
        f"PR #7: {said.format(**names)}",
        NO_LOCAL_CHECK,
    ]


def test_no_batch_comment_or_one_for_another_head_leaves_the_wait(batched: dict[str, str]) -> None:
    head = batched["head"]
    assert queued_merge(head) == [NO_LOCAL_CHECK]
    assert queued_merge(head, batch_note("b" * 40, batched["merge"], batched["batch"])) == [
        NO_LOCAL_CHECK
    ]
    assert queued_merge(head, "> " + batch_note(head, batched["merge"], batched["batch"])) == [
        NO_LOCAL_CHECK
    ]


def test_the_batch_proof_also_stands_in_for_ci(batched: dict[str, str]) -> None:
    head = batched["head"]
    pr = pull(
        reviews=(verdict_on(head),),
        comments=(batch_note(head, batched["merge"], batched["batch"]),),
        checks=(),
    )
    pr["headRefOid"] = head
    assert merge(pr, [approved(1, "area:web")]) == []


def test_batch_posts_the_proof_check_merge_reads(
    batched: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    posted: list[tuple[int, str]] = []
    monkeypatch.setattr(approvals, "comment", lambda number, body: posted.append((number, body)))
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    log = tmp_path / "gate.log"
    log.write_text("".join(f"line {n}\n" for n in range(1, 41)) + "gate: green\n")
    args = [
        "batch",
        "7",
        "--merge",
        batched["merge"],
        "--batch",
        batched["batch"],
        "--exit",
        "0",
        "--log",
        str(log),
    ]
    assert approvals.main(args) == 0
    [(number, body)] = posted
    assert number == 7
    assert body.startswith(
        batch_note(batched["head"], batched["merge"], batched["batch"]).replace(
            "/tmp/gate.log", str(log)
        )
    )
    assert "gate: green" in body and "line 12\n" in body and "line 11\n" not in body
    assert queued_merge(batched["head"], body) == []


@pytest.fixture
def queueing(landing: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """`landing` with `CI: none`, and a local-ci pass recorded on HEAD under the current env."""
    (Path.cwd() / "docs" / "agents" / "loop.md").write_text(GITHUB_RULE + "\nCI: none\n")
    landing["records"] = {HEAD}
    monkeypatch.setattr(
        approvals, "reusable", lambda head: {"head": head} if head in landing["records"] else None
    )
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    return landing


def queue_check(capsys: pytest.CaptureFixture[str], head: str = HEAD) -> tuple[int, list[str]]:
    code = approvals.main(["check", "queue", "7", "--head", head])
    return code, capsys.readouterr().out.splitlines()


def test_a_verified_head_with_its_recorded_pass_may_enter_the_queue(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert queue_check(capsys) == (0, [f"PR #7 may enter a merge queue at {HEAD}"])
    assert queueing["calls"] == []


def test_check_queue_refuses_another_head(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = queue_check(capsys, "c" * 40)
    assert code == 1
    assert f"PR #7's head is {HEAD}, not {'c' * 40}: queue the head the verifier reviewed" in lines


def test_check_queue_refuses_a_head_without_a_recorded_pass(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    queueing["records"] = set()
    assert queue_check(capsys) == (
        1,
        [
            f"PR #7: no `local-ci --record` pass on {HEAD} under this environment (approvals.py local-ci --record)"
        ],
    )


@pytest.mark.parametrize(
    ("labels", "said"),
    [
        (
            ("risk:high",),
            "PR #7 is high risk (`risk:high` is on PR #7): it lands alone through `land`",
        ),
        (
            ("approved:merge",),
            "PR #7 has the owner's `approved:merge`, which covers its head alone: it lands through `land`",
        ),
    ],
)
def test_check_queue_keeps_a_high_risk_or_owner_approved_pr_out(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str], labels: tuple[str, ...], said: str
) -> None:
    queueing["pull"]["labels"]["nodes"] = [{"name": name} for name in labels]
    code, lines = queue_check(capsys)
    assert code == 1
    assert said in lines


def test_check_queue_refuses_a_missing_merge_proof(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    queueing["pull"]["reviews"]["nodes"] = []
    queueing["pull"]["reviewThreads"]["nodes"] = [{"isResolved": False}]
    code, lines = queue_check(capsys)
    assert code == 1
    assert "PR #7: no verifier review posted (approvals.py verdict)" in lines
    assert any("review thread(s) unresolved" in line for line in lines)


def test_with_ci_check_queue_needs_the_heads_check_green(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    (Path.cwd() / "docs" / "agents" / "loop.md").write_text(GITHUB_RULE)
    queueing["records"] = set()
    assert queue_check(capsys) == (0, [f"PR #7 may enter a merge queue at {HEAD}"])
    queueing["pull"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"][0][
        "conclusion"
    ] = "FAILURE"
    code, lines = queue_check(capsys)
    assert code == 1
    assert "PR #7: `check` is FAILURE on the head commit" in lines


def test_queue_and_head_go_together(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    assert approvals.main(["check", "queue", "7"]) == 1
    assert approvals.main(["check", "merge", "7", "--head", HEAD]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "check queue takes a PR number and --head <sha>, the head the queue would merge",
        "--head goes with check queue only",
    ]
