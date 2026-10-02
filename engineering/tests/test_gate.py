"""scripts/gate.py: each loop step leaves proof on GitHub; the gate checks it, and `approve`/`verdict` write it."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

SPEC = importlib.util.spec_from_file_location(
    "gate",
    Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts" / "gate.py",
)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

PROJECT = Path(__file__).resolve().parent / "fixtures" / "loop-project"
TRACKER = (PROJECT / "docs" / "agents" / "issue-tracker.md").read_text()
LOOP = (PROJECT / "docs" / "agents" / "loop.md").read_text()
COMPONENTS = gate.listed(TRACKER, "Components")
CATEGORIES = gate.CATEGORIES | gate.listed(TRACKER, "Extra categories")
HEAD = "a" * 40


@pytest.fixture(autouse=True)
def local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run as on a developer's machine, even inside CI; a test sets GITHUB_ACTIONS itself."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def problems(issues: list[dict[str, Any]]) -> list[str]:
    return gate.problems(issues, COMPONENTS, CATEGORIES)


def node(
    labels: tuple[str, ...] = (), comments: tuple[str, ...] = (), **fields: Any
) -> dict[str, Any]:
    return {
        "labels": {"nodes": [{"name": name} for name in labels]},
        "comments": {"nodes": [{"body": body} for body in comments]},
        **fields,
    }


def issue(
    number: int, *labels: str, body: str = "the spec", comments: tuple[str, ...] = ()
) -> dict[str, Any]:
    return node(labels, comments, number=number, body=body)


def specced(number: int, *labels: str) -> dict[str, Any]:
    return issue(number, "ready-for-agent", "web", "size:S", *labels)


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
    spec = gate.fingerprint(body)
    comments = (record("spec", "coordinator", spec=spec),) + (
        (record("spec", "owner", spec=spec),) if owner else ()
    )
    return issue(
        number, "ready-for-agent", "size:S", "approved:spec", *labels, body=body, comments=comments
    )


def pull(
    *,
    body: str = "## Evidence\n\nlog line\n",
    files: tuple[str, ...] = (),
    comments: tuple[str, ...] = (),
    labels: tuple[str, ...] = (),
    checks: tuple[tuple[str, str], ...] = (("build", "SUCCESS"),),
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
        headRefOid=HEAD,
        files={"nodes": [{"path": path} for path in files]},
        commits={"nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": contexts}}}}]},
        closingIssuesReferences={"nodes": []},
    )


VERDICT = f"Verifier verdict\nHead: {HEAD}\nVERDICT: 0 blocker, 1 major, 0 minor\nSATISFIED: yes\n"
MERGED = (
    VERDICT,
    record("merge", "coordinator", head=HEAD, verdict="VERDICT: 0 blocker; SATISFIED: yes"),
)


# --- labels and state ---


def test_the_tracker_file_lists_components_and_extra_categories_from_their_own_sections() -> None:
    assert (COMPONENTS, CATEGORIES - gate.CATEGORIES) == ({"agents", "api", "web"}, {"ops"})
    assert gate.listed(TRACKER, "Sizes") == set()  # no such section


def test_a_pr_that_closes_no_issue_skipped_the_spec() -> None:
    assert problems([]) == [
        "the PR closes no issue: it needs a `Closes #<spec>` line for a ready-for-agent spec"
    ]


def test_an_intent_or_a_parked_issue_is_named() -> None:
    found = problems(
        [
            specced(1, "bug"),
            issue(2, "chore", "agents", "size:XS"),
            issue(3, "needs-owner", "bug", "api", "size:M"),
            specced(4, "bug", "needs-owner"),
        ]
    )
    assert found == [
        "#2 is not ready-for-agent: triage and spec it first",
        "#3 is not ready-for-agent: triage and spec it first",
        "#3 waits for the owner (needs-owner)",
        "#4 waits for the owner (needs-owner)",
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
    assert problems([issue(58, "wayfinder:task", "ready-for-agent")]) == []
    assert problems([issue(58, "wayfinder:task")]) == [
        "#58 is not ready-for-agent: triage and spec it first"
    ]
    merged = pull(comments=MERGED, labels=("approved:merge",))
    assert gate.proofs("merge", merged, [issue(58, "wayfinder:task")], LOOP) == []


def test_a_specced_issue_without_a_component_or_exactly_one_size_is_named() -> None:
    found = problems([issue(1, "ready-for-agent", "bug"), specced(2, "bug", "size:M")])
    sizes = "size:L, size:M, size:S, size:XL, size:XS"
    assert found == [
        f"#1 needs exactly one size label ({sizes}), has 0",
        "#1 needs a component label (agents, api, web)",
        f"#2 needs exactly one size label ({sizes}), has 2",
    ]


def test_a_tracker_file_without_components_says_so() -> None:
    assert (
        gate.problems([specced(1, "bug")], set())[-1]
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
        ("", []),
        ("See #12; follows #13. Discloses #14, prefix #15, closes owner/repo#16, closes#17", []),
    ],
)
def test_the_body_names_its_closing_issues(body: str, numbers: list[int]) -> None:
    assert gate.named(body) == numbers


# --- approval rules ---


def test_loop_md_rules_and_practice_are_read_from_their_sections() -> None:
    assert gate.rules(LOOP) == [
        ("spec", "size:L or larger, or component `api`"),
        ("merge", "path `billing/**`"),
        ("merge", "a change that can place live orders"),
    ]
    assert not gate.practice_plans(LOOP)
    assert gate.practice_plans("## Practice\n\n- Plan: writing-plans\n")


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
    assert gate.matches(condition, labels, paths) is hit


# --- proof at build ---


def test_an_approved_spec_passes_build() -> None:
    assert gate.proofs("build", pull(), [approved(1, "web")], LOOP) == []


def test_a_spec_nobody_approved_is_named() -> None:
    assert gate.proofs("build", pull(), [specced(1, "bug")], LOOP) == [
        "#1 has no `Approved: spec` record by the coordinator",
        "#1 lacks the `approved:spec` label",
    ]


def test_a_spec_edited_after_its_approval_needs_approving_again() -> None:
    edited = approved(1, "web")
    edited["body"] = "the spec, rewritten"
    assert gate.proofs("build", pull(), [edited], LOOP) == [
        "#1 has no `Approved: spec` record by the coordinator for its current spec: approve again"
    ]


def test_a_matching_rule_needs_the_owner_too() -> None:
    assert gate.proofs("build", pull(), [approved(1, "api")], LOOP) == [
        "#1 has no `Approved: spec` record by the owner"
    ]
    assert gate.proofs("build", pull(), [approved(1, "api", owner=True)], LOOP) == []


def test_a_spec_in_a_comment_is_the_one_approved() -> None:
    spec = "## Spec\n\nthe real spec"
    labels = ("ready-for-agent", "size:S", "web", "approved:spec")
    comments = (spec, record("spec", "coordinator", spec=gate.fingerprint(spec)))
    tool_owned = issue(1, *labels, body="a tool's body", comments=comments)
    assert gate.proofs("build", pull(), [tool_owned], LOOP) == []


def test_a_due_plan_needs_its_comment_and_approval() -> None:
    plans = "## Practice\n\n- Plan: writing-plans\n"
    assert gate.proofs("build", pull(), [approved(1, "web")], plans) == [
        "#1 has no `## Plan` comment, and one is due"
    ]
    assert (
        gate.proofs("build", pull(), [approved(1, "web")], "## Approvals\n\n- plan: always\n") == []
    )
    planned = approved(1, "web")
    planned["comments"]["nodes"].append({"body": "## Plan\n\n1. slice"})
    assert gate.proofs("build", pull(), [planned], "") == [
        "#1 has no `Approved: plan` record by the coordinator",
        "#1 lacks the `approved:plan` label",
    ]


# --- proof at merge ---


def test_a_pr_with_every_proof_passes_merge() -> None:
    checks = (("build", "SUCCESS"), ("gate", "SUCCESS"))
    done = pull(comments=MERGED, labels=("approved:merge",), checks=checks)
    assert gate.proofs("merge", done, [approved(1, "web")], LOOP) == []


def test_inside_github_actions_the_other_checks_are_their_own_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    running = pull(
        comments=MERGED,
        labels=("approved:merge",),
        checks=(("build", "IN_PROGRESS"), ("gate", "IN_PROGRESS")),
    )
    assert gate.proofs("merge", running, [approved(1, "web")], LOOP) == [
        "PR #7: CI check `build` is IN_PROGRESS on the head commit",
        "PR #7: CI check `gate` is IN_PROGRESS on the head commit",
    ]
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert gate.proofs("merge", running, [approved(1, "web")], LOOP) == []


def test_without_ci_the_merge_proof_is_a_local_check_recorded_on_the_head() -> None:
    no_ci = LOOP + "\nCI: none\n"
    missing = [
        (
            "PR #7: the project has no CI (loop.md `CI: none`), and no local check passed on"
            " the head (gate.py record-check)"
        )
    ]

    def proofs(*comments: str) -> list[str]:
        merged = pull(comments=(*MERGED, *comments), labels=("approved:merge",), checks=())
        return gate.proofs("merge", merged, [approved(1, "web")], no_ci)

    assert (
        proofs(),
        proofs(f"{gate.CHECKED}\nHead: {'b' * 40}\nCommand: mise run check\n"),
        proofs("## Evidence\n\n- `mise run check`: exit 0\n"),
        proofs(f"{gate.CHECKED}: no, not run\nHead: {HEAD}\n"),
        proofs(f"> {gate.CHECKED}\n> Head: {HEAD}\n"),
        proofs(f"{gate.CHECKED}\nHead: {HEAD}\nCommand: mise run check\n"),
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
    assert (re.search(gate.NO_CI, f"## Gates\n\n{line}\n", re.MULTILINE) is not None) == opted_out


def test_a_merge_record_without_its_verdict_is_no_approval() -> None:
    headless = (VERDICT, record("merge", "coordinator", head=HEAD))
    assert gate.proofs(
        "merge", pull(comments=headless, labels=("approved:merge",)), [approved(1, "web")], LOOP
    ) == [
        "PR #7 has no `Approved: merge` record by the coordinator for its current head: approve again"
    ]


def test_more_checks_than_one_page_is_refused() -> None:
    big = pull(comments=MERGED, labels=("approved:merge",))
    big["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["totalCount"] = 101
    assert gate.proofs("merge", big, [approved(1, "web")], LOOP) == [
        "PR #7 has more than 1 CI checks: the gate reads one page",
    ]


def test_more_files_than_one_page_is_refused_only_where_a_merge_path_rule_needs_them() -> None:
    big = pull(comments=MERGED, labels=("approved:merge",))
    big["files"]["totalCount"] = 101
    no_path_rule = "## Approvals\n\n- spec: size:L or larger\n"
    assert (
        gate.proofs("build", big, [approved(1, "web")], LOOP),
        gate.proofs("merge", big, [approved(1, "web")], no_path_rule),
    ) == ([], [])
    with pytest.raises(gate.Refused, match="more than 0 changed files: the gate reads one page"):
        gate.proofs("merge", big, [approved(1, "web")], LOOP)


def test_more_comments_than_one_page_is_refused(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    crowded = pull(comments=MERGED, labels=("approved:merge",))
    crowded["comments"]["totalCount"] = 101
    crowded["closingIssuesReferences"]["nodes"] = [approved(1, "web")]
    monkeypatch.setattr(gate, "pull_request", lambda _n: crowded)
    monkeypatch.chdir(PROJECT)
    assert (gate.main(["check", "merge", "7"]), capsys.readouterr().out) == (
        1,
        "#7 has more than 2 comments: the gate reads one page\n",
    )


def test_a_path_rule_on_the_spec_is_left_to_the_loop() -> None:
    rule = "## Approvals\n\n- spec: path `billing/**`\n"
    assert gate.proofs("build", pull(files=("billing/a.py",)), [approved(1, "web")], rule) == []


def test_a_pr_without_its_proof_names_each_missing_one() -> None:
    bare = pull(
        body="## Evidence\n\n## Summary\n", checks=(("build", "FAILURE"), ("lint", "IN_PROGRESS"))
    )
    assert gate.proofs("merge", bare, [approved(1, "web")], LOOP) == [
        "PR #7: its body has no `## Evidence` section with content",
        "PR #7: no verifier verdict posted (gate.py verdict)",
        "PR #7: CI check `build` is FAILURE on the head commit",
        "PR #7: CI check `lint` is IN_PROGRESS on the head commit",
        "PR #7 has no `Approved: merge` record by the coordinator",
        "PR #7 lacks the `approved:merge` label",
    ]
    assert "PR #7: no CI check on the head commit" in gate.proofs("merge", pull(checks=()), [], "")


def test_a_push_after_the_merge_approval_needs_approving_again() -> None:
    old = (VERDICT, record("merge", "coordinator", head="b" * 40, verdict="VERDICT: 0 blocker"))
    assert gate.proofs(
        "merge", pull(comments=old, labels=("approved:merge",)), [approved(1, "web")], LOOP
    ) == [
        "PR #7 has no `Approved: merge` record by the coordinator for its current head: approve again"
    ]


def test_a_merge_rule_on_a_path_needs_the_owner_and_free_text_is_left_to_the_loop() -> None:
    plain = pull(comments=MERGED, labels=("approved:merge",))
    assert gate.proofs("merge", plain, [approved(1, "web")], LOOP) == []
    billing = pull(files=("billing/invoice.py",), comments=MERGED, labels=("approved:merge",))
    assert gate.proofs("merge", billing, [approved(1, "web")], LOOP) == [
        "PR #7 has no `Approved: merge` record by the owner"
    ]


# --- writing proof ---


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Every write gate.py makes, instead of making it."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        gate, "comment", lambda number, body: calls.append(("comment", number, body))
    )
    monkeypatch.setattr(
        gate, "label", lambda number, name, add: calls.append(("label", number, name, add))
    )
    monkeypatch.chdir(PROJECT)
    return calls


def test_the_coordinator_approves_a_spec_no_rule_holds(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "issue_node", lambda _n: specced(1, "bug"))
    assert gate.main(["approve", "spec", "1", "--by", "coordinator"]) == 0
    assert github == [
        ("comment", 1, f"Approved: spec\nBy: coordinator\nSpec: {gate.fingerprint('the spec')}\n"),
        ("label", 1, "approved:spec", True),
    ]


def test_a_rule_leaves_the_label_to_the_owner(
    github: list[tuple[Any, ...]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        gate, "issue_node", lambda _n: specced(1, "bug", "size:XL", "approved:spec")
    )
    assert gate.main(["approve", "spec", "1", "--by", "coordinator"]) == 0
    assert github[1:] == [("label", 1, "approved:spec", False), ("label", 1, "needs-owner", True)]
    assert "stop until they add `approved:spec`" in capsys.readouterr().out
    github.clear()
    assert gate.main(["approve", "spec", "1", "--by", "owner"]) == 0
    assert github[1:] == [("label", 1, "approved:spec", True), ("label", 1, "needs-owner", False)]


def test_resuming_after_the_owner_approved_keeps_their_label(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = (
        VERDICT,
        record("merge", "owner", head=HEAD, verdict="VERDICT: 0 blocker; SATISFIED: yes"),
    )
    pr = pull(files=("billing/invoice.py",), comments=owned, labels=("approved:merge",))
    pr["closingIssuesReferences"]["nodes"] = [specced(1, "bug")]
    monkeypatch.setattr(gate, "pull_request", lambda _n: pr)
    assert gate.main(["approve", "merge", "7", "--by", "coordinator"]) == 0
    assert github[1:] == [("label", 7, "approved:merge", True)]


def test_a_merge_approval_carries_the_head_and_the_verdict(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    pr = pull(comments=(VERDICT,))
    pr["closingIssuesReferences"]["nodes"] = [specced(1, "bug")]
    monkeypatch.setattr(gate, "pull_request", lambda _n: pr)
    assert (
        gate.main(
            ["approve", "merge", "7", "--by", "coordinator", "--triage", "https://x/7#triage"]
        )
        == 0
    )
    assert github == [
        (
            "comment",
            7,
            (
                f"Approved: merge\nBy: coordinator\nHead: {HEAD}\n"
                "Verdict: VERDICT: 0 blocker, 1 major, 0 minor; SATISFIED: yes\nTriage: https://x/7#triage\n"
            ),
        ),
        ("label", 7, "approved:merge", True),
    ]


def test_a_merge_approval_needs_a_posted_verdict(
    github: list[tuple[Any, ...]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(gate, "pull_request", lambda _n: pull())
    assert gate.main(["approve", "merge", "7", "--by", "coordinator"]) == 1
    assert (github, capsys.readouterr().out) == (
        [],
        "PR #7 has no verifier verdict: post it first (gate.py verdict)\n",
    )


def test_the_verdict_posts_the_reports_last_lines(
    github: list[tuple[Any, ...]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(gate, "pull_request", lambda _n: pull())
    report = tmp_path / "report.md"
    report.write_text("findings\nVERDICT: 0 blocker, 1 major, 0 minor\nSATISFIED: yes\n")
    assert gate.main(["verdict", "7", str(report)]) == 0
    assert github == [("comment", 7, VERDICT)]
    report.write_text("findings, unfinished\n")
    assert gate.main(["verdict", "7", str(report)]) == 1
    assert (
        capsys.readouterr().out == f"{report} has no `SATISFIED:` line: the report is unfinished\n"
    )


# --- check end to end, GitHub stubbed ---


def test_check_without_a_pr_has_nothing_to_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gate, "current_pr", lambda: None)
    monkeypatch.chdir(PROJECT)
    assert (gate.main(["check", "build"]), capsys.readouterr().out) == (
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

    monkeypatch.setattr(gate, "pull_request", refused)
    monkeypatch.chdir(PROJECT)
    assert (gate.main(["check", "build", "1"]), capsys.readouterr().out) == (
        1,
        "gh: Could not resolve to an issue or pull request with the number of 9.\n",
    )


def test_run_outside_a_repo_with_a_tracker_file_fails_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert (gate.main(["check", "build", "1"]), capsys.readouterr().out) == (
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
    monkeypatch.setattr(gate, "pull_request", lambda _pr: pr)
    monkeypatch.chdir(tmp_path)
    assert (gate.main(["check", "build", "7"]), capsys.readouterr().out) == (0, "")


# --- record-check: the local check, run on the PR head ---


@pytest.fixture
def checkout(github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A checkout at the PR head and clean; a test changes it, or what the check does to it."""
    state: dict[str, Any] = {"head": HEAD, "status": "", "exit": 0, "after": None}

    def git(*args: str) -> str:
        if args[0] == "rev-parse":
            return state["head"] + "\n"
        assert args == (
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        return state["status"]

    def run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        assert (command, check) == (["mise", "run", "check"], False)
        if state["after"]:
            state["status"] = state["after"]
        return subprocess.CompletedProcess(command, state["exit"])

    monkeypatch.setattr(gate, "pull_request", lambda _n: pull())
    monkeypatch.setattr(gate, "git", git)
    monkeypatch.setattr(gate.subprocess, "run", run)
    return state


def test_a_passing_check_on_the_clean_head_is_recorded(
    github: list[tuple[Any, ...]], checkout: dict[str, Any]
) -> None:
    assert gate.main(["record-check", "7"]) == 0
    assert github == [("comment", 7, f"{gate.CHECKED}\nHead: {HEAD}\nCommand: mise run check\n")]


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"head": "b" * 40}, f"the checkout is at {'b' * 40}, PR #7's head is {HEAD}"),
        ({"status": " M app.py\n"}, "the tree has changes"),
        ({"exit": 2}, "mise run check exited 2: nothing recorded"),
        ({"after": " M uv.lock\n"}, "mise run check changed the checkout"),
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
    assert gate.main(["record-check", "7"]) == 1
    assert github == []
    assert said in capsys.readouterr().out


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


@pytest.mark.parametrize("hide", [hidden_untracked, hidden_submodule_edit])
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
    monkeypatch.setattr(gate, "pull_request", lambda _n: {**pull(), "headRefOid": head})
    monkeypatch.chdir(repo)
    assert gate.main(["record-check", "7"]) == 1
    assert github == []
    assert "the tree has changes" in capsys.readouterr().out
