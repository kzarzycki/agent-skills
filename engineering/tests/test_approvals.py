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
        author={"login": "worker"},
        state="OPEN",
        isDraft=False,
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
        "#2 has no `Approved: spec` record by the owner",
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
    merged = pull(reviews=(VERDICT,), labels=OWNED)
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
        ("size:L or larger, or component `api`", {"size:S", "api"}, [], True),
        ("category ops", {"bug"}, [], False),
        ("path `billing/**`", set(), ["billing/a/invoice.py"], True),
        ("path `billing/**`", set(), ["web/app.ts"], False),
        ("path `billing/**`", set(), None, None),
        ("size:L+ or path `billing/**`", {"size:XL"}, None, True),
        ("path .github/**", set(), [".github/ci.yml"], True),
        ("path .github/**", set(), ["README.md"], False),
        ("path: .github/**, or component `api`", {"api"}, ["README.md"], True),
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
    assert approvals.proofs("build", pull(), [approved(1, "web")], LOOP) == []


def test_a_spec_nobody_approved_is_named() -> None:
    assert approvals.proofs("build", pull(), [specced(1, "bug")], "") == [
        "#1 has no `Approved: spec` record by the owner",
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
    assert approvals.proofs("build", pull(), [approved(1, "api")], "") == []


def test_a_spec_in_a_comment_is_the_one_approved() -> None:
    spec = "## Spec\n\nthe real spec"
    labels = ("ready-for-agent", "size:S", "web", "approved:spec")
    edited = "2026-10-02T11:00:00Z"
    comments = (
        note(spec, lastEditedAt=edited),
        record("spec", "owner", spec="as edited 2026-10-02 11:00:00 UTC"),
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
    assert approvals.proofs("build", pull(), [planned], "") == []  # no agent approves a plan either
    assert approvals.proofs("build", pull(), [planned], "## Approvals\n\n- plan: always\n") == [
        "#1 has no `Approved: plan` record by the owner",
        "#1 lacks the `approved:plan` label",
    ]


# --- proof at merge ---


def test_a_pr_with_every_proof_passes_merge() -> None:
    checks = (("check", "SUCCESS"), ("pr-board / sync", "FAILURE"))
    done = pull(reviews=(VERDICT,), labels=OWNED, checks=checks)
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
    assert merge(stale, [approved(1, "web")]) == [
        "PR #7: `approved:merge` was added before the head was pushed: the owner adds it again"
    ]
    same_second = pull(reviews=(VERDICT,), labels=OWNED, labeled=PUSHED, files=billing)
    assert merge(same_second, [approved(1, "web")]) == [
        "PR #7: `approved:merge` was added before the head was pushed: the owner adds it again"
    ]
    monkeypatch.setattr(approvals, "head_pushed", lambda _pull: None)
    assert merge(pull(reviews=(VERDICT,), labels=OWNED, files=billing), [approved(1, "web")]) == [
        f"PR #7: GitHub lists no push of the head {HEAD}, so `approved:merge` can't be dated after it"
    ]


def test_a_label_added_again_after_the_push_is_the_approval() -> None:
    again = pull(reviews=(VERDICT,), labels=OWNED)
    again["timelineItems"]["nodes"] = [
        {"createdAt": "2026-10-01T09:00:00Z", "label": {"name": "approved:merge"}},
        {"createdAt": LABELED, "label": {"name": "approved:merge"}},
    ]
    assert merge(again, [approved(1, "web")]) == []


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
    big = pull(reviews=(VERDICT,), labels=OWNED, checks=(("lint", "SUCCESS"),))
    big["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["totalCount"] = 101
    assert merge(big, [approved(1, "web")]) == [
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
        approvals.proofs("build", pull(files=("billing/a.py",)), [approved(1, "web")], rule) == []
    )


def test_a_pr_without_its_proof_names_each_missing_one() -> None:
    bare = pull(
        body="## Evidence\n\n## Summary\n", checks=(("check", "FAILURE"),), files=("billing/a.py",)
    )
    assert merge(bare, [approved(1, "web")]) == [
        "PR #7: its body has no `## Evidence` section with content",
        "PR #7: no verifier review posted (approvals.py verdict)",
        "PR #7: `check` is FAILURE on the head commit",
        BILLING,
    ]
    assert "PR #7: no `check` on the head commit yet" in merge(pull(checks=()), [], "")


def test_a_legacy_merge_rule_in_loop_md_reads_as_a_risk_rule() -> None:
    rule = "## Approvals\n\n- merge: path `billing/**`\n"
    billing = pull(files=("billing/invoice.py",), reviews=(VERDICT,))
    assert merge(billing, [approved(1, "web")], rule) == [BILLING]
    assert merge(pull(files=("web/app.ts",), reviews=(VERDICT,)), [approved(1, "web")], rule) == []
    billing["labels"]["nodes"] = [{"name": "approved:merge"}]
    billing["timelineItems"]["nodes"] = [
        {"createdAt": LABELED, "label": {"name": "approved:merge"}}
    ]
    assert merge(billing, [approved(1, "web")], rule) == []


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
    monkeypatch.setattr(approvals, "issue_node", lambda _n: specced(1, "bug", "needs-owner"))
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
    edited = specced(1, "bug", "size:XL")
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
    old = specced(1, "bug")
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
            "The doc.\n\nVERDICT: 1 blocker, 0 major, 2 minor\nSATISFIED: no\n"
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
    return approvals.proofs("merge", pr, [approved(1, "web")], LOOP)


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
    # a pass on a later commit supersedes those on an earlier one
    assert verified(verdict_on(OLD, "1 blocker, 0 major, 0 minor", satisfied="no"), VERDICT) == []


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
            " left a core finding open, so the owner decides"
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
            " left a core finding open, so the owner decides"
        )
    ]


def test_only_a_review_by_the_prs_author_or_the_viewer_counts(
    monkeypatch: pytest.MonkeyPatch,
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


def test_without_a_user_token_only_the_prs_authors_review_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installation token (the approvals workflow's `github.token`) can't read `GET /user`: the gate trusts the
    PR's author, the shared account, instead of failing every PR with a verifier review."""

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


def test_more_reviews_or_threads_than_one_page_is_refused() -> None:
    crowded = pull(reviews=(VERDICT,), threads=(True,))
    crowded["reviews"]["totalCount"] = 101
    crowded["reviewThreads"]["totalCount"] = 101
    assert approvals.proofs("merge", crowded, [approved(1, "web")], LOOP) == [
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
        return approvals.waits(pr, [approved(1, "web")], loop)

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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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


def test_land_turns_on_auto_merge_while_required_checks_are_pending(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"] = {
        **landing["pull"],
        **pull(reviews=(VERDICT,), checks=(("check", "IN_PROGRESS"),)),
    }
    landing["pull"]["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
    landing.update(change, pull=pr)
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (approvals.WAITING, [])
    assert line in lines


def test_a_base_with_no_required_checks_gets_no_auto_merge_while_a_check_is_pending(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """GitHub would merge an auto-merge request at once on a base that requires nothing, pending checks or not."""
    landing["rulesets"] = []
    pr = pull(reviews=(VERDICT,), checks=(("check", "IN_PROGRESS"),))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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
        ({"issue": issue(1, "web", "bug", "size:S")}, "#1 lacks the `approved:spec` label"),
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
    found = change.pop("issue", approved(1, "web", "bug"))
    pr = pull(**{"reviews": (VERDICT,), "files": ("app.py",), **change})
    pr["closingIssuesReferences"]["nodes"] = [found]
    landing["pull"] = pr
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (1, [])
    assert line in lines


def test_land_says_a_merged_pr_is_merged_and_refuses_a_closed_one(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"]["state"] = "MERGED"
    assert landed(capsys, landing) == (0, ["PR #7 is merged"], [])
    landing["pull"]["state"] = "CLOSED"
    assert landed(capsys, landing) == (1, ["PR #7 is closed: nothing to land"], [])


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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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
    merged = pull(reviews=(VERDICT,), comments=tuple(posted), labels=OWNED, checks=())
    assert merge(merged, [approved(1, "web")], LOOP + "\nCI: none\n") == []


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


# --- the owner's policy: specs approved and merges landed without an agent's approval ---

POLICY = "## Approvals\n\n- spec: auto unless risk\n- merge: auto unless risk\n- risk: path `billing/**`\n"
EDITED = "2026-10-02T14:35:27Z"


def epic(*labels: str, by: str = "owner", **fields: Any) -> dict[str, Any]:
    """An epic as an issue's GraphQL `parent`, with `by`'s spec record of its first version."""
    found = issue(9, "enhancement", *labels, comments=(record("spec", by, spec=AS_WRITTEN),))
    return {**found, **fields}


def story(
    parent: dict[str, Any], author: str | None = "worker", body: str = "the spec"
) -> dict[str, Any]:
    """A native sub-issue of `parent`, opened by `author`, with no approval of its own."""
    found = issue(1, "enhancement", "web", "size:S", body=body)
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
        (issue(1, "bug"), True),
        (
            issue(1, "enhancement", body="The rate.\n\nFound while #12 reviewing the invoice.\n"),
            True,
        ),
        (issue(1, "enhancement", body="- Found while #12, a follow-up\n"), True),
        (issue(1, "enhancement", body="An example: `Found while #12`\n"), False),
        (issue(1, "enhancement", body="The template:\n\n```\nFound while #12\n```\n"), False),
        (issue(1, "enhancement", body="`Found while #12` is the line.\n"), False),
        (issue(1, "bug", "epic"), False),
        (issue(1, "enhancement", body="It was found while #12 ran.\n"), False),
        (story(epic("approved:spec")), True),
        (story(epic("approved:spec"), author="drive-by"), False),
        (story(epic("approved:spec"), author=None), False),
        (story(epic()), False),
        (story(epic("approved:spec", by="coordinator")), False),
        (story(epic("approved:spec", lastEditedAt=EDITED)), False),
        (issue(1, "enhancement", "epic"), False),
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
        specced(1, "bug"),
        story(epic("approved:spec")),
        specced(3, "enhancement", "epic"),
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
    assert problems([specced(1, "bug", "needs-owner")]) == ["#1 waits for the owner (needs-owner)"]


def test_a_policy_line_is_no_condition_so_a_low_risk_pr_waits_for_nothing() -> None:
    done = pull(reviews=(VERDICT,), files=("app.py",))
    assert merge(done, [specced(1, "bug")], POLICY) == []
    assert approvals.risk(done, [specced(1, "bug")], POLICY) is None


def test_a_low_risk_agent_pr_lands_with_no_approval_record_and_no_label(
    landing: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    added: list[tuple[int, str, bool]],
) -> None:
    Path("docs/agents/loop.md").write_text(LOOP)
    follow_up = issue(
        1, "enhancement", "web", "size:S", body="The fix.\n\nFound while #5 landing.\n"
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
    found = approved(1, "web", *issue_labels)
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
    signed["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
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
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "web", "bug")]
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.chdir(PROJECT)
    capped_line = (
        HELD
        + "a verifier review at the cap (pass 5) or later left a core finding open, so the owner decides"
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
