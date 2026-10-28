"""scripts/approvals.py: each loop step leaves proof on GitHub; the gate checks it, and `approve`/`verdict` write it."""

from __future__ import annotations

import fnmatch
import importlib.util
import itertools
import json
import re
import subprocess
import sys
import textwrap
from collections.abc import Callable
from datetime import UTC, datetime
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


def loop_md(settings: str = "") -> str:
    """A loop.md whose settings block holds `settings`, YAML."""
    return f"# Loop facts\n\n## Settings\n\n```yaml\n{settings}```\n\nThe prose for people.\n"


BARE = loop_md()  # a loop.md with no settings, so no rules


def add(loop: str, section: str, settings: str) -> str:
    """`loop` with `settings`, keys written flush left, added to its `section`, made at the block's end where it has
    none."""
    header, settings = f"\n{section}:\n", textwrap.indent(settings, "  ")
    if header in loop:
        return loop.replace(header, header + settings, 1)
    end = loop.index("```", loop.index("```yaml\n") + len("```yaml\n"))
    return loop[:end] + header[1:] + settings + loop[end:]


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
REQUIRED = approvals.required_checks
MERGED_HIGH = approvals.merged_high
COMMENT = approvals.comment


@pytest.fixture(autouse=True)
def pushed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The head was pushed at PUSHED, before the PR's labels were added (LABELED), and the directory a test runs in
    is the checkout's root; a test says otherwise."""
    monkeypatch.setattr(approvals, "head_pushed", lambda _pull: PUSHED)
    monkeypatch.setattr(approvals, "toplevel", Path.cwd)
    monkeypatch.setattr(approvals, "viewer", lambda: "loop")
    monkeypatch.setattr(approvals, "merged_high", lambda _branch: [])


@pytest.fixture(autouse=True)
def required(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The base branch requires no checks, instead of reading its rules; the list holds each base asked about."""
    asked: list[str] = []
    monkeypatch.setattr(approvals, "required_checks", lambda base: asked.append(base) or set())
    return asked


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
        "author": {"login": "loop"},
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
    comments: tuple[str | dict[str, Any], ...] = (),
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
        baseRepository={
            "nameWithOwner": "kzarzycki/scratch-gate-revert",
            "defaultBranchRef": {"name": "main"},
        },
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
    assert approvals.label_names(
        loop_md('components:\n  area:web: ""\ncategories:\n  kind:ops: ""\n')
    ) == {
        "category": approvals.CATEGORIES | {"kind:ops"},
        "component": {"area:web"},
        "size": approvals.SIZES,
    }


@pytest.mark.parametrize(
    ("settings", "refused"),
    [
        ('sizes:\n  XXL: ""\n', "issue-tracker.md has an unknown settings section `sizes`"),
        ("components: api\n", "issue-tracker.md has a setting `components` outside a section"),
        ("[components]\napi\n", "issue-tracker.md's settings block is not YAML"),
        (
            "components:\n  api: 1\n",
            "issue-tracker.md's `components.api` must be a string, not 1",
        ),
    ],
)
def test_a_tracker_block_off_its_schema_is_refused_naming_the_key(
    settings: str, refused: str
) -> None:
    with pytest.raises(approvals.Refused) as raised:
        approvals.label_names(loop_md(settings))
    assert str(raised.value).startswith(refused)
    with pytest.raises(approvals.Refused, match="issue-tracker.md has no ```yaml settings block"):
        approvals.label_names("## Components\n\n- `billing`: invoices.\n")


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


def test_check_build_before_the_pr_judges_the_issue(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no PR yet, `check build --issue <n>` (or the issue the branch is named for) applies the PR's build proofs
    to the issue alone, so an unapproved spec is not built."""
    spec: dict[int, dict[str, Any]] = {
        2: issue(2, "kind:chore", "area:agents", "size:XS", "risk:high"),
        3: approved(3, "kind:chore", "area:agents"),
    }
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, LOOP))
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    monkeypatch.setattr(approvals, "issue_node", lambda n: spec[n])
    monkeypatch.setattr(approvals, "current_pr", lambda: None)
    branch, changed = ["loop/3-fix"], [""]

    def git(*args: str) -> str:
        if args[0] == "diff":
            assert args == ("diff", "--name-only", "-z", "origin/main...HEAD")
            if changed[0] is None:
                raise subprocess.CalledProcessError(128, ["git", *args])
            return "".join(f"{path}\0" for path in changed[0].split())
        return ("origin/main" if args[-1] == "origin/HEAD" else branch[0]) + "\n"

    monkeypatch.setattr(approvals, "git", git)

    def build(*args: str) -> tuple[int, list[str]]:
        code = approvals.main(["check", "build", *args])
        return code, capsys.readouterr().out.splitlines()

    unapproved = [
        "#2 has no `Approved: spec` record by the owner",
        "#2 lacks the `approved:spec` label",
    ]
    assert build("--issue", "2") == (1, unapproved)
    assert build("--issue", "3") == (0, ["#3: every build proof holds; no PR yet"])
    assert build() == (0, ["#3: every build proof holds; no PR yet"])
    branch[0] = "loop/2-fix"
    assert build() == (1, unapproved)
    branch[0] = "spike"
    assert build()[0] == 1
    assert build("7", "--issue", "2") == (1, ["--issue goes with check build and no PR number"])


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
        approvals.problems([specced(1, "kind:bug")], approvals.label_names(BARE))[-1]
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


def test_loop_md_settings_are_read_from_its_yaml_block() -> None:
    assert approvals.settings(LOOP) == {
        "spec": {"auto": ["bug", "follow-up", "sub-issue"]},
        "practice": {"spec": "to-spec"},
        "risk": {
            "labels": ["size:L", "size:XL", "area:api"],
            "paths": ["billing/**", ".github/**"],
        },
    }
    assert approvals.settings(None) == approvals.settings(BARE) == {}
    commented = loop_md(
        "# a comment\nloop:\n  cap: 3  # passes\nrisk:\n  paths:\n    # a note\n    - a/**\n"
    )
    assert approvals.settings(commented) == {"cap": 3, "risk": {"paths": ["a/**"]}}
    bots = loop_md(
        "bot:\n  dependabot[bot]:\n    paths:\n      - uv.lock\n  renovate[bot]:\n    paths:\n      - a\n      - b\n"
    )
    assert approvals.settings(bots)["bot"] == [
        {"login": "dependabot[bot]", "paths": ["uv.lock"]},
        {"login": "renovate[bot]", "paths": ["a", "b"]},
    ]
    # only the first yaml block is the settings: a later one is an example in the prose
    later = loop_md("loop:\n  cap: 3\n") + "```yaml\nloop:\n  cap: 4\n```\n"
    assert approvals.settings(later) == {"cap": 3}


@pytest.mark.parametrize(
    ("settings", "refused"),
    [
        ("loop:\n  caps: 3\n", "loop.md has an unknown setting `loop.caps`"),
        ("risk:\n  path:\n    - a/**\n", "loop.md has an unknown setting `risk.path`"),
        ("plan:\n  paths:\n    - a/**\n", "loop.md has an unknown setting `plan.paths`"),
        (
            "practice:\n  reviews: code-review\n",
            "loop.md has an unknown setting `practice.reviews`",
        ),
        ("approvals:\n  spec: auto\n", "loop.md has an unknown settings section `approvals`"),
        ("spec: auto\n", "loop.md has a setting `spec` outside a section"),
        (
            "bot:\n  paths:\n    - uv.lock\n",
            "loop.md's `bot.paths` must be a section holding `paths`",
        ),
        (
            "loop:\n  cap: three\n",
            "loop.md's `loop.cap` must be a whole number, not 'three'",
        ),
        ("loop:\n  cap: true\n", "loop.md's `loop.cap` must be a whole number, not True"),
        ('loop:\n  ci: "false"\n', "loop.md's `loop.ci` must be true or false, not 'false'"),
        (
            "spec:\n  auto: auto unless risk\n",
            "loop.md's `spec.auto` must be true, false or a list of bug, follow-up, sub-issue, not 'auto unless risk'",
        ),
        (
            "spec:\n  auto:\n    - bugs\n",
            "loop.md's `spec.auto` must be true, false or a list of bug, follow-up, sub-issue, not ['bugs']",
        ),
        ("loop:\n  spec: auto\n", "loop.md has an unknown setting `loop.spec`"),
        (
            "risk:\n  labels: size:L, size:XL\n",
            "loop.md's `risk.labels` must be a list of strings, not 'size:L, size:XL'",
        ),
        (
            "risk:\n  labels:\n    - 1\n",
            "loop.md's `risk.labels` must be a list of strings, not [1]",
        ),
        ("bot:\n  dependabot[bot]:\n", "loop.md's `bot.dependabot[bot]` lacks `paths`"),
        ("land:\n  signed_squash_to: main\n", "loop.md's `land` lacks `allowed_signers`"),
        (
            'land:\n  signed_squash_to: ""\n  allowed_signers: s\n',
            "loop.md's `land.signed_squash_to` is empty",
        ),
    ],
)
def test_settings_that_do_not_match_the_schema_are_refused_naming_the_key(
    settings: str, refused: str
) -> None:
    with pytest.raises(approvals.Refused) as raised:
        approvals.settings(loop_md(settings))
    assert str(raised.value) == refused


def test_a_loop_md_without_its_settings_block_or_with_one_that_is_not_yaml_is_refused() -> None:
    """A project still on the line form would otherwise lose its risk rules unnoticed."""
    with pytest.raises(approvals.Refused, match="loop.md has no ```yaml settings block"):
        approvals.settings("## Approvals\n\n- risk: path `.github/**`\n")
    for broken in ("loop:\n  cap: 3\n ci: true\n", "risk:\n  paths: [a/**\n", "loop:\n\tcap: 3\n"):
        with pytest.raises(approvals.Refused, match="loop.md's settings block is not YAML:"):
            approvals.settings(loop_md(broken))
    with pytest.raises(approvals.Refused, match="loop.md's settings block is not YAML sections"):
        approvals.settings(loop_md("- loop\n"))
    for twice, key in (
        ("loop:\n  cap: 3\n  cap: 4\n", "loop.cap"),
        ("risk: {}\nrisk: {}\n", "risk"),
    ):
        with pytest.raises(approvals.Refused, match=f"loop.md's `{key}` is set twice"):
            approvals.settings(loop_md(twice))


@pytest.mark.parametrize(
    ("settings", "refused"),
    [
        ("practice:\n  plan: no\n", "loop.md's `practice.plan` must be a string, not False"),
        ("practice:\n  plan: 1.10\n", "loop.md's `practice.plan` must be a string, not 1.1"),
        (
            "risk:\n  labels:\n    - on\n",
            "loop.md's `risk.labels` must be a list of strings, not [True]",
        ),
        (
            "loop:\n  local_ci_env:\n    - 1.10\n",
            "loop.md's `loop.local_ci_env` must be a list of strings",
        ),
        ("loop:\n  ci: off-ish\n", "loop.md's `loop.ci` must be true or false, not 'off-ish'"),
        ("bot:\n  yes:\n    paths: []\n", "loop.md's `bot.True` is no name: quote it"),
    ],
)
def test_what_yaml_1_1_reads_as_another_type_is_refused_naming_the_key(
    settings: str, refused: str
) -> None:
    """PyYAML follows YAML 1.1: `no`, `on` and `yes` are booleans and `1.10` the number 1.1, never the name written."""
    with pytest.raises(approvals.Refused) as raised:
        approvals.settings(loop_md(settings))
    assert str(raised.value).startswith(refused)
    quoted = settings.replace("no\n", '"no"\n').replace("1.10", '"1.10"').replace("on\n", '"on"\n')
    if quoted != settings:
        approvals.settings(loop_md(quoted))


def test_a_tracker_name_yaml_reads_as_a_boolean_is_refused_naming_it() -> None:
    with pytest.raises(
        approvals.Refused, match="issue-tracker.md's `components.True` is no name: quote it"
    ):
        approvals.label_names(loop_md("components:\n  on: the on-call rota.\n"))
    assert (
        "area:on"
        in approvals.label_names(loop_md('components:\n  "on": the on-call rota.\n'))["component"]
    )


def test_skill_mds_settings_examples_pass_their_schema() -> None:
    """SKILL.md § Settings shows loop.md's block, then issue-tracker.md's: each is what the scripts read."""
    skill = (SCRIPTS.parent / "SKILL.md").read_text()
    loop, tracker = re.findall(
        r"^```yaml\n(.*?)^```$", skill[skill.index("### Settings") :], re.DOTALL | re.MULTILINE
    )[:2]
    assert approvals.settings(loop_md(loop))["bot"] == [
        {"login": "dependabot[bot]", "paths": ["uv.lock", "**/package.json"]},
        {"login": "renovate", "branch": "renovate/", "paths": ["uv.lock"]},
    ]
    assert approvals.tracker_settings(loop_md(tracker))["renames"] == {"frontend": "area:web"}
    excepted = approvals.settings(loop_md(loop))["carry_over_main"]["except"]
    # a glob matches the full path: a nested copy needs a glob of its own
    for path in ("uv.lock", "engineering/uv.lock"):
        assert any(fnmatch.fnmatch(path, glob) for glob in excepted), path


def test_a_script_run_without_pyyaml_says_in_one_line_how_to_run_it() -> None:
    """`-S` leaves out site-packages, where PyYAML is installed, as a bare `python3` without it would."""
    run = subprocess.run(
        [sys.executable, "-S", str(SCRIPTS / "approvals.py"), "check", "build"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert run.returncode == 1
    assert run.stderr.splitlines() == [
        f"approvals.py needs PyYAML: run it with `uv run {SCRIPTS / 'approvals.py'}`, which installs it"
    ]


EXAMPLE = "## Example\n\n```yaml\nloop:\n  ci: false\n```\n\n"


def test_a_yaml_example_outside_settings_is_never_read_as_the_settings() -> None:
    """Only the block under `## Settings` is read: an example in the prose neither replaces nor stands in for it."""
    document = EXAMPLE + loop_md("loop:\n  ci: true\nrisk:\n  always: true\n")
    assert approvals.settings(document)["ci"] is True
    assert approvals.ruled(set(), [], document) == "it matches a risk rule (always)"
    with pytest.raises(approvals.Refused, match="loop.md has no ```yaml settings block"):
        approvals.settings("## Approvals\n\n- risk: always\n\n" + EXAMPLE)
    tracker = EXAMPLE + loop_md("components:\n  billing: invoices\n")
    assert approvals.label_names(tracker)["component"] == {"area:billing"}
    with pytest.raises(approvals.Refused, match="issue-tracker.md has no ```yaml settings block"):
        approvals.label_names("## Components\n\n- `billing`: invoices.\n\n" + EXAMPLE)


@pytest.mark.parametrize(
    ("terms", "labels", "paths", "hit"),
    [
        ({"always": True}, set(), [], "always"),
        ({"always": False}, set(), [], False),
        ({"labels": ["size:L", "size:XL"]}, {"size:XL"}, [], "label `size:XL`"),
        ({"labels": ["size:L"]}, {"size:XL"}, [], False),
        ({"labels": ["area:api"]}, {"api"}, [], False),
        ({"labels": ["kind:bug"]}, {"kind:bug"}, [], "label `kind:bug`"),
        ({"paths": ["billing/**"]}, set(), ["billing/a/invoice.py"], "path `billing/**`"),
        ({"paths": ["billing/**"]}, set(), ["web/app.ts"], False),
        ({"paths": ["billing/**"]}, set(), None, None),
        ({"labels": ["size:XL"], "paths": ["billing/**"]}, {"size:XL"}, None, "label `size:XL`"),
        ({"paths": ["docs/*.md"]}, set(), ["docs/a.md"], "path `docs/*.md`"),
        ({"paths": ["a dir/**"]}, set(), ["a dir/b, c.py"], "path `a dir/**`"),
        ({"verifier": True}, set(), [], False),
        ({}, {"size:XL"}, None, False),
    ],
)
def test_a_rule_holds_on_its_first_matching_term_or_is_left_to_the_loop(
    terms: dict[str, Any], labels: set[str], paths: list[str] | None, hit: str | bool | None
) -> None:
    assert approvals.matches(terms, labels, paths) == hit


def test_a_path_naming_the_verifier_is_no_verifier_term() -> None:
    """The line form searched the rule's text for `verifier`, so a path holding the word held every PR the verifier
    judged high; the gate now reads the `verifier` field alone."""
    loop = loop_md("risk:\n  paths:\n    - docs/verifier.md\n")
    assert (
        approvals.ruled(set(), ["app.py"], loop, "the verifier's pass 1 says `Risk: high`") is None
    )
    assert (
        approvals.ruled(set(), ["docs/verifier.md"], loop)
        == "it matches a risk rule (path `docs/verifier.md`)"
    )


# --- proof at build ---


def test_an_approved_spec_passes_build() -> None:
    assert approvals.proofs("build", pull(), [approved(1, "area:web")], LOOP) == []


def test_a_spec_nobody_approved_is_named() -> None:
    assert approvals.proofs("build", pull(), [specced(1, "kind:bug")], BARE) == [
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
    assert approvals.proofs("build", pull(), [agents], BARE) == [
        "#1 has no `Approved: spec` record by the owner"
    ]
    assert approvals.proofs("build", pull(), [approved(1, "area:api")], BARE) == []


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
    plans = loop_md("practice:\n  plan: writing-plans\n")
    assert approvals.proofs("build", pull(), [approved(1, "area:web")], plans) == [
        "#1 has no `## Plan` comment, and one is due"
    ]
    assert (
        approvals.proofs(
            "build", pull(), [approved(1, "area:web")], loop_md("plan:\n  always: true\n")
        )
        == []
    )
    planned = approved(1, "area:web")
    planned["comments"]["nodes"].append(note("## Plan\n\n1. slice"))
    assert (
        approvals.proofs("build", pull(), [planned], BARE) == []
    )  # no agent approves a plan either
    assert approvals.proofs("build", pull(), [planned], loop_md("plan:\n  always: true\n")) == [
        "#1 has no `Approved: plan` record by the owner",
        "#1 lacks the `approved:plan` label",
    ]


# --- proof at merge ---


def test_a_pr_with_every_proof_passes_merge() -> None:
    checks = (("check", "SUCCESS"), ("pr-board / sync", "FAILURE"))
    done = pull(reviews=(VERDICT,), labels=OWNED, checks=checks)
    assert merge(done, [approved(1, "area:web")]) == []


def test_a_demo_linked_instead_of_embedded_fails_check_merge_naming_demo_sh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(approvals, "writer", lambda login: login == "loop")
    embedded = (
        "## Demo\n\nthe preview, on aaaaaaa.\nhttps://github.com/user-attachments/assets/0b1c-2d\n"
    )
    asset = "https://github.com/kzarzycki/omnigent/releases/download/demo-190/check-1.mp4"
    linked = f"## Demo\n\n- [check 1]({asset})\n"
    issues = [approved(1, "area:web")]
    done = {"reviews": (VERDICT,), "labels": OWNED}
    assert merge(pull(comments=(embedded,), **done), issues) == []
    failed = merge(pull(comments=(embedded, linked), **done), issues)
    assert len(failed) == 1 and asset in failed[0] and "`scripts/demo.sh`" in failed[0]
    assert "embeds no video" in merge(pull(comments=("## Demo\n\nsee the PR",), **done), issues)[0]
    # at build too, once a demo is posted; a stranger's demo comment holds nothing
    assert approvals.proofs("build", pull(comments=(linked,)), issues, LOOP) == failed
    stranger = note(linked, author={"login": "drive-by"})
    assert merge(pull(comments=(embedded, stranger), **done), issues) == []


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


DELEGATED = note(record("merge", "delegate"), createdAt="2026-10-01T11:00:01Z")


def test_a_delegated_label_approves_a_merge_into_a_feature_branch_only() -> None:
    """The delegate's record is newer than the label it names; the owner's label added after it is the owner's."""
    high = ("risk:high", "approved:merge")
    into_main = pull(reviews=(VERDICT,), labels=high, comments=(DELEGATED,))
    assert merge(into_main, [approved(1, "area:web")]) == [
        (
            "PR #7: `approved:merge` is the delegated approval, which covers a PR into a feature branch, not into"
            " main: the owner removes it and adds it again"
        )
    ]
    into_feature = pull(reviews=(VERDICT,), labels=high, comments=(DELEGATED,))
    into_feature["baseRefName"] = "stream"
    assert merge(into_feature, [approved(1, "area:web")]) == []
    owners = pull(reviews=(VERDICT,), labels=high, comments=(DELEGATED,))
    owners["timelineItems"]["nodes"].append(
        {"createdAt": "2026-10-01T12:00:00Z", "label": {"name": "approved:merge"}}
    )
    assert merge(owners, [approved(1, "area:web")]) == []


def test_a_branchs_merge_to_the_default_branch_carries_its_high_risk_prs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    monkeypatch.setattr(approvals, "merged_high", lambda branch: asked.append(branch) or [12, 15])
    assert merge(pull(reviews=(VERDICT,)), [approved(1, "area:web")]) == [
        HELD + "`risk:high` is on #12, merged into feature, #15, merged into feature"
    ]
    into_feature = pull(reviews=(VERDICT,))
    into_feature["baseRefName"] = "stream"
    assert merge(into_feature, [approved(1, "area:web")]) == []
    assert asked == ["feature"]
    monkeypatch.undo()
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(approvals, "gh", lambda *args: calls.append(args) or "12\n15\n")
    assert approvals.merged_high("feature") == [12, 15]
    assert calls == [
        (
            "pr",
            "list",
            "--base",
            "feature",
            "--state",
            "merged",
            "--label",
            "risk:high",
            "--limit",
            "100",
            "--json",
            "number",
            "--jq",
            ".[].number",
        )
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


@pytest.mark.parametrize(
    ("base", "checks", "lines"),
    [
        ({"qualify"}, (("qualify", "SUCCESS"),), []),
        (
            {"qualify"},
            (("check", "SUCCESS"), ("qualify", "FAILURE")),
            ["PR #7: `qualify` is FAILURE on the head commit"],
        ),
        ({"qualify"}, (("check", "SUCCESS"),), ["PR #7: no `qualify` on the head commit yet"]),
        # a base that requires nothing: the aggregate `check` alone, not land's every check
        (set(), (("check", "SUCCESS"), ("lint", "FAILURE")), []),
        (set(), (("lint", "SUCCESS"),), ["PR #7: no `check` on the head commit yet"]),
        # the shipped ruleset: `loop:approvals` is check merge's own output, never something it waits for
        ({"check", approvals.APPROVALS}, (("check", "SUCCESS"),), []),
        ({approvals.APPROVALS}, (("check", "SUCCESS"),), []),
        (
            {approvals.APPROVALS},
            (("lint", "SUCCESS"),),
            ["PR #7: no `check` on the head commit yet"],
        ),
    ],
)
def test_check_merge_waits_for_the_checks_the_base_branch_requires(
    monkeypatch: pytest.MonkeyPatch,
    required: list[str],
    base: set[str],
    checks: tuple[tuple[str, str], ...],
    lines: list[str],
) -> None:
    """check merge reads the base's required checks as land does, once."""
    monkeypatch.setattr(approvals, "required_checks", lambda name: required.append(name) or base)
    pr = pull(reviews=(VERDICT,), checks=checks)
    assert approvals.waits(pr, [approved(1, "area:web")], LOOP) == lines
    assert required == ["main"]


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


def test_a_high_risk_change_needs_a_default_tier_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """A satisfied lower-tier verdict saying `Risk: high` blocks the merge; a default-tier verdict on the same head
    clears it, and a heading naming no tier reads as the default."""
    monkeypatch.setattr(approvals, "writer", lambda _login: False)
    judged = add(loop_md("spec:\n  auto: true\n"), "risk", "verifier: true\n")

    def said(family: str, number: int, risk: str) -> dict[str, Any]:
        heading = f"Verifier ({family}), pass {number}"
        return verdict_on(HEAD, "0 blocker, 0 major, 0 minor", heading=heading) | {
            "body": f"{heading} on {HEAD[:7]}.\n\nVERDICT: 0 blocker, 0 major, 0 minor\nSATISFIED: yes\nRisk: {risk}\n"
        }

    def gate(*reviews: dict[str, Any]) -> list[str]:
        return approvals.proofs(
            "merge",
            pull(reviews=reviews, labels=OWNED),
            [approved(1, "kind:bug", "area:web")],
            judged,
        )

    assert gate(said("codex/terra-6.1/med mid", 1, "high — CI permissions")) == [
        (
            "PR #7 is high risk (it matches a risk rule's `verifier` term: the verifier's pass 1 on aaaaaaa says"
            " `Risk: high — CI permissions`), and its newest verdict came from a lower tier (mid): a default-tier"
            " verifier pass on the head first"
        )
    ]
    assert (
        gate(said("codex/terra-6.1/med mid", 1, "high"), said("codex/sol-6.1/med", 2, "high")) == []
    )
    assert gate(said("codex/terra-6.1/med mid", 1, "low — a fixture")) == []
    assert gate(said("codex", 1, "high")) == []
    # a tier word inside the model id is no tier: only a word of its own after the signature is
    assert gate(said("codex/sol-mid-preview/med", 1, "high")) == []
    assert gate(said("claude/small-model/?, same-family", 1, "high")) == []
    assert gate(said("claude, same-family, small", 1, "high"))


def test_without_ci_the_merge_proof_is_a_local_check_recorded_on_the_head() -> None:
    no_ci = add(LOOP, "loop", "ci: false\n")
    missing = [
        (
            "PR #7: the project has no CI (loop.md `ci: false`), and no local check passed on"
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


def test_a_local_check_counts_only_from_the_author_the_runner_or_a_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anyone can comment on a public repo, so a `Local check passed` comment from an account without write access
    proves nothing."""
    no_ci = add(LOOP, "loop", "ci: false\n")
    monkeypatch.setattr(approvals, "writer", lambda login: login == "maintainer")
    passed = f"{approvals.CHECKED}\nHead: {HEAD}\nCommand: mise run check:all\n"

    def proofs(login: str) -> list[str]:
        merged = pull(
            reviews=(VERDICT,), comments=(note(passed, author={"login": login}),), labels=OWNED
        )
        return merge(merged, [approved(1, "area:web")], no_ci)

    assert proofs("stranger") == [
        (
            "PR #7: the project has no CI (loop.md `ci: false`), and no local check passed on the"
            " head (approvals.py local-ci)"
        )
    ]
    assert proofs("loop") == proofs("maintainer") == proofs("worker") == []


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
        approvals.ran(crowded, loop_md("loop:\n  ci: false\n"))


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
    assert "PR #7: no `check` on the head commit yet" in merge(pull(checks=()), [], BARE)


def test_a_risk_path_rule_holds_only_a_pr_touching_its_path() -> None:
    rule = loop_md("risk:\n  paths:\n    - billing/**\n")
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

SIGNOFF = add(LOOP, "signoff", "labels:\n  - area:web\npaths:\n  - app/**\n")
LANDED = pull(reviews=(VERDICT,), labels=OWNED)


def linking(keyword: str, number: int = 1, files: tuple[str, ...] = ()) -> dict[str, Any]:
    return pull(
        body=f"{keyword} #{number}\n\n## Evidence\n\nlog line\n",
        reviews=(VERDICT,),
        labels=OWNED,
        files=files,
    )


def test_the_signoff_rule_is_read_from_the_settings_and_is_no_risk_rule() -> None:
    assert approvals.settings(SIGNOFF)["signoff"] == {"labels": ["area:web"], "paths": ["app/**"]}
    assert approvals.settings(SIGNOFF)["risk"] == approvals.settings(LOOP)["risk"]


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
            " (label `area:web`): the PR says `Implements #1`, which leaves it open,"
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


def test_signoff_paths_past_the_files_the_gate_reads_ask_for_the_signoff() -> None:
    def crowded(keyword: str) -> dict[str, Any]:
        pr = linking(keyword, files=("README.md",))
        pr["files"]["totalCount"] = 101
        return pr

    assert approvals.linked(crowded("Implements"), [approved(1, "area:api")], SIGNOFF) == []
    assert approvals.linked(crowded("Closes"), [approved(1, "area:api")], SIGNOFF)[0].startswith(
        "#1 waits for the owner's sign-off after landing, since the gate can't read every file the PR"
        " changes, so the sign-off rule's `paths` hold"
    )


def test_signoff_always_asks_for_implements_and_a_rule_matching_nothing_asks_for_none() -> None:
    web = approved(1, "area:web")
    assert approvals.linked(linking("Closes"), [web], add(LOOP, "signoff", "always: true\n"))[
        0
    ].startswith("#1 waits for the owner's sign-off after landing")
    nothing = add(LOOP, "signoff", "labels:\n  - area:nothing\n")
    assert approvals.linked(linking("Closes"), [web], nothing) == []


def test_a_wayfinder_ticket_and_a_repo_without_loop_md_are_not_checked() -> None:
    ticket = issue(58, "wayfinder:task", "approved:spec", "area:web")
    assert approvals.linked(linking("Closes", 58), [ticket], SIGNOFF) == []
    assert approvals.proofs("merge", linking("Closes"), [approved(1, "area:web")], None) == []


# --- an exact revert ---

# GitHub's REST answers from a scratch round trip, trimmed to what the gate reads where noted: #1 merged (pull-1.json
# trimmed), #2 the PR GitHub's Revert button made for it after main moved, #3 that revert plus one line, still open;
# #2's and #3's merge base (trimmed) and the trees (trimmed to path, mode, SHA and type) of #1's base and merge
# commit and of the reverts' merge base and heads.
REVERTED = Path(__file__).resolve().parent / "fixtures" / "reverts"
REVERT_BASE, REVERT_HEAD = (
    "340b9aa38acac5a0d84e8c6d276a6ed2f3afdbe4",
    "47e28a794ff0884f8631342b8ed1aae4733e1ba6",
)
HEADS = {2: REVERT_HEAD, 3: "89cfd913d7696aafeb9cd6b4ac444aa131717e5b"}
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
        "headRefOid": HEADS.get(number, REVERT_HEAD),
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


def held_revert(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    revert: dict[str, Any],
    original: dict[str, Any],
    loop: str = BARE,
) -> tuple[int, list[str]]:
    """check merge on an exact revert of `original` (#1), by default under a loop.md with no risk rule, so only the
    risk of what it reverts can hold it."""
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, loop))
    monkeypatch.setattr(approvals, "pull_request", lambda n: original if n == 1 else revert)
    code = approvals.main(["check", "merge", str(revert["number"])])
    return code, capsys.readouterr().out.splitlines()


def test_an_exact_revert_of_a_high_risk_change_waits_for_the_owners_label(
    recorded: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The risk of the change a revert undoes (or re-lands) carries over: `risk:high` on an issue the revert closes,
    on the PR it reverts, or that PR's last verdict saying `Risk: high`."""
    low = {**pull(), "number": 1}
    held = "PR #2 waits for the owner's `approved:merge` label, since it is high risk: "
    closing = revert_pr(body=REVERT_BODY + "\nCloses #71\n")
    closing["closingIssuesReferences"] = {"nodes": [specced(71, "kind:bug", "risk:high")]}
    assert held_revert(monkeypatch, capsys, closing, low) == (
        approvals.WAITING,
        [held + "`risk:high` is on #71"],
    )
    high = {**pull(labels=("risk:high",)), "number": 1}
    assert held_revert(monkeypatch, capsys, revert_pr(), high) == (
        approvals.WAITING,
        [held + "`risk:high` is on #1, which it reverts"],
    )
    said = "Verifier (codex), pass 2\n\nVERDICT: 0 blocker, 0 major, 0 minor\nSATISFIED: yes\nRisk: high — CI permissions\n"
    judged = {**pull(reviews=(verdict_on(HEAD) | {"body": said},)), "number": 1}
    assert held_revert(monkeypatch, capsys, revert_pr(), judged) == (
        approvals.WAITING,
        [
            held
            + "it reverts #1, and the verifier's pass 2 on aaaaaaa says `Risk: high — CI permissions`"
        ],
    )
    # a risk rule reads the labels of the issues a revert names, as for any PR
    ruled = revert_pr(body=REVERT_BODY + "\nCloses #71\n")
    ruled["closingIssuesReferences"] = {"nodes": [specced(71, "kind:bug")]}
    web = add(BARE, "risk", "labels: [area:web]\n")
    assert held_revert(monkeypatch, capsys, ruled, low, web) == (
        approvals.WAITING,
        [held + "it matches a risk rule (label `area:web`)"],
    )
    # the owner's label clears each, and a revert of a low-risk PR lands without it
    assert held_revert(monkeypatch, capsys, revert_pr(labels=OWNED), high) == (0, [])
    assert held_revert(monkeypatch, capsys, revert_pr(), low) == (0, [])


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
    assert approvals.inexact(original, revert, 1, KEPT, MOVED) == []
    moved = revert[:1] + [entry("new.py", "@@ -1 +1 @@\n-y\n+x")]
    assert approvals.inexact(original, moved, 1, KEPT, MOVED) == [
        "it changes `new.py`, which #1 did not",
        "it leaves `old.py -> new.py` as #1 changed it",
    ]


def test_a_file_github_shows_no_diff_of_is_no_exact_revert() -> None:
    assert approvals.inexact(
        [entry("logo.png", None)], [entry("logo.png", None)], 1, KEPT, MOVED
    ) == [
        "GitHub shows no diff of `logo.png` to compare",
        "GitHub shows no diff of `logo.png` to compare",
    ]
    unchanged = {"filename": "run.sh", "status": "modified", "changes": 0, "patch": ""}
    assert approvals.inexact([unchanged], [unchanged], 1, KEPT, MOVED) == [
        "GitHub shows no diff of `run.sh` to compare",
        "GitHub shows no diff of `run.sh` to compare",
    ]


def test_a_missing_final_newline_counts() -> None:
    assert approvals.changed_lines("@@ -1 +1 @@\n-x\n\\ No newline at end of file\n+x") == [
        (["x"], ["x\n\\ no newline"])
    ]


CALLS = "@@ -1,2 +1,2 @@\n-authorize()\n-transfer()\n+authorize_v2()\n+transfer_v2()"
UNDO_CALLS = "@@ -3,2 +3,2 @@\n-authorize_v2()\n-transfer_v2()\n+authorize()\n+transfer()"
PATHS = ("a.py", "new.py", "old.py", "logo.png", "run.sh", "app.py")


def at(*blobs: str) -> tuple[dict[str, tuple[str, str]], ...]:
    """Trees holding every path with mode 100644, the nth tree's blobs named blobs[n]."""
    return tuple({path: ("100644", blob) for path in PATHS} for blob in blobs)


# #1's base and merge commit trees, and the revert's merge base and head after main changed the files since, so the
# trees can't show the inverse and the diffs decide; every mode kept
KEPT, MOVED = at("before", "after"), at("main", "head")


def test_the_inverse_keeps_the_order_of_changed_lines() -> None:
    original = [entry("app.py", CALLS)]
    assert approvals.inexact(original, [entry("app.py", UNDO_CALLS)], 1, KEPT, MOVED) == []
    swapped = UNDO_CALLS.replace("+authorize()\n+transfer()", "+transfer()\n+authorize()")
    assert approvals.inexact(original, [entry("app.py", swapped)], 1, KEPT, MOVED) == [
        "`app.py` changes the lines #1 changed in another order"
    ]
    # the same lines in the same order, one of them moved into another run
    two = [entry("app.py", "@@ -1,3 +1,3 @@\n-a\n+b\n x\n-c\n+d")]
    moved = [entry("app.py", "@@ -1,3 +1,3 @@\n-b\n+a\n+c\n x\n-d")]
    assert approvals.inexact(two, moved, 1, KEPT, MOVED) == [
        "`app.py` changes the lines #1 changed in another order"
    ]


def test_a_revert_that_restores_the_trees_is_exact_whatever_order_its_diff_shows() -> None:
    """A `git revert` of #1 with no later change to its files: GitHub's diff pairs the restored lines another way
    (#351), but the head holds #1's base blobs, so the change is undone."""
    original = [entry("app.py", CALLS)]
    swapped = [
        entry(
            "app.py", UNDO_CALLS.replace("+authorize()\n+transfer()", "+transfer()\n+authorize()")
        )
    ]
    restored = (KEPT[1], KEPT[0])
    assert approvals.inexact(original, swapped, 1, KEPT, restored) == []
    # a head that keeps a line of #1 holds another blob, so the diffs decide
    kept = (KEPT[1], {**KEPT[0], "app.py": ("100644", "kept")})
    assert approvals.inexact(original, swapped, 1, KEPT, kept) == [
        "`app.py` changes the lines #1 changed in another order"
    ]
    # a file #1 did not change is no part of its revert, whatever the trees hold
    extra = swapped + [entry("run.sh", "@@ -1 +1 @@\n-a\n+b")]
    assert approvals.inexact(original, extra, 1, KEPT, restored) == [
        "`app.py` changes the lines #1 changed in another order",
        "it changes `run.sh`, which #1 did not",
    ]


def test_a_revert_that_changes_a_mode_is_no_exact_revert() -> None:
    exact = ([entry("app.py", CALLS)], [entry("app.py", UNDO_CALLS)], 1)
    assert approvals.inexact(
        *exact, KEPT, (MOVED[0], {**MOVED[1], "app.py": ("100755", "head")})
    ) == ["`app.py` has mode 100755 at the head, and 100644 before #1"]
    for truncated in ((None, MOVED[1]), (MOVED[0], None)):
        assert approvals.inexact(*exact, truncated, MOVED) == [
            "GitHub truncates a tree it would compare file modes in"
        ]
        assert approvals.inexact(*exact, KEPT, truncated) == [
            "GitHub truncates a tree it would compare file modes in"
        ]


def test_a_revert_that_also_undoes_a_later_mode_change_is_no_exact_revert() -> None:
    """#1 kept app.py's mode, main made it executable after, and the revert branches from there and resets it: its
    head has app.py's mode from before #1, but it undoes main's change too."""
    exact = ([entry("app.py", CALLS)], [entry("app.py", UNDO_CALLS)], 1)
    assert approvals.inexact(
        *exact, KEPT, ({**MOVED[0], "app.py": ("100755", "main")}, MOVED[1])
    ) == ["`app.py` has mode 100755 at the merge base, and 100644 after #1"]


def test_an_empty_file_left_in_place_is_no_exact_revert() -> None:
    added = {"filename": "run.sh", "status": "added", "changes": 0}
    moded = {"filename": "run.sh", "status": "modified", "changes": 0}
    assert approvals.inexact(
        [added],
        [moded],
        1,
        ({}, {"run.sh": ("100644", "empty")}),
        ({"run.sh": ("100644", "empty")}, {"run.sh": ("100755", "empty")}),
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


def test_a_post_naming_a_term_of_the_local_deny_list_is_refused_before_any_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The list names private terms; a body that names one, in any case and as a whole word, is refused naming the
    term and the line, and nothing reaches gh. Without the variable, nothing changes."""
    calls: list[list[str]] = []
    monkeypatch.setattr(
        approvals.subprocess,
        "run",
        lambda command, **_kw: calls.append(command) or subprocess.CompletedProcess(command, 0, ""),
    )
    deny = tmp_path / "deny.txt"
    deny.write_text(
        "# private names\nAcme-Widgets\nacme/secret-repo  # its repo\nbuild-host.local\n"
    )
    monkeypatch.setenv("LOOP_DENY_LIST", str(deny))
    for body, term, line in [
        ("Fixed.\nSeen in ACME-WIDGETS's run.\n", "Acme-Widgets", 2),
        ("See acme/secret-repo#12.\n", "acme/secret-repo", 1),
        ("Ran on build-host.local\n", "build-host.local", 1),
    ]:
        with pytest.raises(approvals.Refused) as refused:
            approvals.comment(7, body)
        assert str(refused.value) == (
            f"refused to post: line {line} names `{term}` from the deny list (LOOP_DENY_LIST); nothing posted"
        )
    with pytest.raises(approvals.Refused, match="names `Acme-Widgets`"):
        approvals.post_review(7, {"body": "pass 1 on acme-widgets"})
    # a review is JSON: the text GitHub publishes is checked, not its escaped form (`\nAcme`, `Caf\u00e9`)
    deny.write_text("Acme-Widgets\nCafé\n")
    for review, term, line in [
        ({"body": "Safe heading\nAcme-Widgets is listed"}, "Acme-Widgets", 2),
        (
            {
                "body": "Safe",
                "comments": [{"path": "x.py", "line": 1, "body": "Safe\n\nSeen in café"}],
            },
            "Café",
            3,
        ),
    ]:
        with pytest.raises(approvals.Refused) as refused:
            approvals.post_review(7, review)
        assert f"line {line} names `{term}`" in str(refused.value)
    assert calls == []
    # a term inside a longer word is no match
    approvals.comment(7, "Acme-Widgetsmith and xacme/secret-repo are fine.\n")
    assert len(calls) == 1
    monkeypatch.delenv("LOOP_DENY_LIST")
    approvals.comment(7, "Seen in Acme-Widgets's run.\n")
    assert len(calls) == 2
    monkeypatch.setenv("LOOP_DENY_LIST", str(tmp_path / "missing.txt"))
    with pytest.raises(approvals.Refused, match="can't be read"):
        approvals.comment(7, "anything")
    assert len(calls) == 2


def test_verdict_refuses_a_report_naming_a_listed_term_before_reading_github(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deny, report = tmp_path / "deny.txt", tmp_path / "report.md"
    deny.write_text("Acme-Widgets\n")
    monkeypatch.setenv("LOOP_DENY_LIST", str(deny))
    report.write_text(REPORT.replace("The doc.", "Seen in Acme-Widgets."))
    read: list[str] = []
    monkeypatch.setattr(approvals, "pull_request", lambda _n: read.append("pull") or pull())
    monkeypatch.setattr(approvals, "diff_lines", lambda *_a: read.append("diff") or {})
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    assert approvals.main(["verdict", "7", str(report)]) == 1
    assert "names `Acme-Widgets` from the deny list" in capsys.readouterr().out
    assert read == []


@pytest.mark.parametrize(
    ("actor", "at", "said"),
    [
        (
            "octocat",
            LABELED,
            "#1: recorded the owner's `approved:spec`, added after the spec's last edit, as their approval",
        ),
        (
            "octocat",
            "2026-10-01T08:00:00Z",
            (
                f"#1: the owner's `approved:spec` was added before the spec's last edit ({AS_WRITTEN}): the owner"
                " adds it again"
            ),
        ),
        ("someone", LABELED, None),
    ],
    ids=["the owner after the edit", "the owner before it", "another account"],
)
def test_the_owners_own_label_after_the_last_edit_is_their_approval(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    actor: str,
    at: str,
    said: str | None,
) -> None:
    """With loop.md's `owner`, the owner's `approved:spec` added after the spec's last edit is recorded as their word
    and `needs-owner` comes off, so the gate proceeds; an older label or anyone else's leaves the refusal."""
    loop = add(LOOP, "loop", "owner: octocat\n")
    spec = issue(1, "kind:enhancement", "area:web", "size:S", "needs-owner", "approved:spec")
    spec["timelineItems"] = {
        "nodes": [
            {
                "__typename": "LabeledEvent",
                "createdAt": at,
                "actor": {"__typename": "User", "login": actor},
                "label": {"name": "approved:spec"},
            }
        ]
    }

    def label(number: int, name: str, add: bool) -> None:
        held = [node for node in spec["labels"]["nodes"] if node["name"] != name]
        spec["labels"]["nodes"] = held + [{"name": name}] * add

    monkeypatch.setattr(approvals, "label", label)
    monkeypatch.setattr(
        approvals, "comment", lambda _n, body: spec["comments"]["nodes"].append(note(body))
    )
    monkeypatch.setattr(approvals, "issue_node", lambda _n: spec)
    pr = pull()
    pr["closingIssuesReferences"] = {"nodes": [spec]}
    found, _issues = approvals.gated("merge", pr, TRACKER, loop)
    if actor == "octocat" and at == LABELED:
        assert found == ["PR #7: no verifier review posted (approvals.py verdict)"]
        assert "needs-owner" not in approvals.names(spec)
    else:
        assert found[:2] == [
            "#1 waits for the owner (needs-owner)",
            "#1 has no `Approved: spec` record by the owner",
        ]
    assert capsys.readouterr().out.splitlines() == ([said] if said else [])


def test_check_build_before_the_pr_records_the_owners_own_label(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`check build --issue <n>`, before a PR exists, adopts the owner's own label as the PR path does."""
    loop = add(LOOP, "loop", "owner: octocat\n")
    spec = issue(1, "kind:enhancement", "area:web", "size:S", "needs-owner", "approved:spec")
    spec["timelineItems"] = {
        "nodes": [
            {
                "__typename": "LabeledEvent",
                "createdAt": LABELED,
                "actor": {"__typename": "User", "login": "octocat"},
                "label": {"name": "approved:spec"},
            }
        ]
    }

    def label(number: int, name: str, add: bool) -> None:
        held = [node for node in spec["labels"]["nodes"] if node["name"] != name]
        spec["labels"]["nodes"] = held + [{"name": name}] * add

    monkeypatch.setattr(approvals, "label", label)
    monkeypatch.setattr(
        approvals, "comment", lambda _n, body: spec["comments"]["nodes"].append(note(body))
    )
    monkeypatch.setattr(approvals, "issue_node", lambda _n: spec)
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, loop))
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    monkeypatch.setattr(
        approvals, "git", lambda *args: "" if args[0] == "diff" else "origin/main\n"
    )
    assert approvals.main(["check", "build", "--issue", "1"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "#1: recorded the owner's `approved:spec`, added after the spec's last edit, as their approval",
        "#1: every build proof holds; no PR yet",
    ]


def test_an_edit_after_the_owners_label_is_never_recorded_under_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The spec is read again to record it: an edit between the check and the record is refused, not approved, and
    loop.md's owner matches the label's actor whatever its casing, as GitHub's logins do."""
    loop = add(LOOP, "loop", "owner: Octocat\n")
    spec = issue(1, "kind:enhancement", "area:web", "size:S", "needs-owner", "approved:spec")
    spec["timelineItems"] = {
        "nodes": [
            {
                "__typename": "LabeledEvent",
                "createdAt": LABELED,
                "actor": {"__typename": "User", "login": "octocat"},
                "label": {"name": "approved:spec"},
            }
        ]
    }
    later = {**spec, "lastEditedAt": "2026-10-01T12:00:00Z"}
    sent: list[str] = []
    monkeypatch.setattr(approvals, "label", lambda *args, **kwargs: sent.append("label"))
    monkeypatch.setattr(approvals, "comment", lambda _n, body: sent.append(body))
    monkeypatch.setattr(approvals, "issue_node", lambda _n: later)
    with pytest.raises(
        approvals.Refused, match=r"edited \(as edited 2026-10-01 12:00:00 UTC\) after the owner"
    ):
        approvals.adopted([spec], loop)
    assert sent == []
    monkeypatch.setattr(approvals, "issue_node", lambda _n: spec)
    approvals.adopted([spec], loop)
    assert sent[0] == f"Approved: spec\nBy: owner\nSpec: {AS_WRITTEN}\n"


def test_approve_refuses_the_coordinator(
    github: list[tuple[Any, ...]], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        approvals.main(["approve", "spec", "1", "--by", "coordinator"])
    assert exited.value.code == 2
    assert "invalid choice: 'coordinator'" in capsys.readouterr().err
    assert github == []


def test_delegate_labels_then_records_a_feature_branch_pr_and_refuses_the_default_branch(
    github: list[tuple[Any, ...]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pr = pull()
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    assert approvals.main(["delegate", "7"]) == 1
    assert capsys.readouterr().out == (
        "PR #7 targets main, the default branch: only the owner approves its merge\n"
    )
    assert github == []
    pr["baseRefName"] = "stream"
    assert approvals.main(["delegate", "7"]) == 0
    assert github == [
        ("label", 7, "approved:merge", True),
        ("comment", 7, "Approved: merge\nBy: delegate\n"),
    ]


def test_delegate_takes_its_label_off_again_when_the_record_fails(
    github: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A label without its record would read as the owner's once the PR is retargeted to the default branch."""
    pr = pull()
    pr["baseRefName"] = "stream"
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)

    def failing(number: int, body: str) -> None:
        raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 503: Service Unavailable")

    monkeypatch.setattr(approvals, "comment", failing)
    assert approvals.main(["delegate", "7"]) == 1
    assert github == [
        ("label", 7, "approved:merge", True),
        ("label", 7, "approved:merge", False),
    ]


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


@pytest.mark.parametrize(
    "heading",
    [
        "Verifier (codex), pass 5",
        "Verifier (codex/terra-6.1/med), pass 5",
        "Verifier (cc/opus-5.5/?, same-family), pass 5",
    ],
)
@pytest.mark.parametrize("marker", ["", "> 🤖 AI\n\n"])
def test_a_review_or_comment_is_found_with_or_without_a_signature_and_the_ai_marker(
    heading: str, marker: str
) -> None:
    review = verdict_on(HEAD, heading=heading)
    assert approvals.PASS.match(review["body"])[2] == "5"
    note = {"body": f"{marker}{heading}\n\nbody", "author": {"login": "loop"}}
    assert approvals.headed({"comments": {"nodes": [note]}}, heading) is not None


def test_a_report_whose_verifier_line_names_a_signature_becomes_the_headings_family(
    tmp_path: Path,
) -> None:
    report = tmp_path / "r.md"
    report.write_text(REPORT.replace("claude, same-family, pass 2", "codex/terra-6.1/med, pass 5"))
    assert approvals.parse_report(report)[0] == "Verifier (codex/terra-6.1/med), pass 5"


def test_a_qualifier_after_the_pass_number_is_posted_in_the_reviews_first_line(
    reviewing: list[tuple[Any, ...]], tmp_path: Path
) -> None:
    """Text after `pass <n>` on the `Verifier:` line is accepted and posted, so a qualifier the project asks for needs
    no line or comment of its own; the heading the gate reads stays `Verifier (<family>), pass <n>`."""
    report = tmp_path / "report.md"
    report.write_text(
        REPORT.replace(
            "Verifier: claude, same-family, pass 2",
            "Verifier: claude, same-family, pass 2 (merge of main; the other family is out of quota)",
        )
    )
    assert approvals.main(["verdict", "7", str(report)]) == 0
    (_, _asked), (_, _pr, review) = reviewing
    first = review["body"].splitlines()[0]
    assert first == (
        f"Verifier (claude, same-family), pass 2 on {HEAD[:7]}: (merge of main; the other family is out of quota)."
    )
    assert approvals.PASS.match(review["body"]).groups() == ("claude, same-family", "2")
    assert review["comments"][0]["body"].startswith(
        "**Verifier (claude, same-family), pass 2 · C1**"
    )


@pytest.mark.parametrize("qualifier", [": note, pass 12", "(redoes Verifier (other), pass 12)"])
def test_a_qualifier_naming_another_pass_never_changes_the_pass(
    tmp_path: Path, qualifier: str
) -> None:
    report = tmp_path / "report.md"
    line = "Verifier: claude, same-family, pass 2"
    report.write_text(REPORT.replace(line, f"{line} {qualifier}"))
    heading, *_rest, said = approvals.parse_report(report)
    assert approvals.PASS.match(heading).groups() == ("claude, same-family", "2")
    assert said == qualifier.lstrip(": ")


def test_brief_fills_the_facts_from_the_pr_and_refuses_a_stale_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The base is the merge-base with the default branch, the head the PR's, the pass one after the newest verdict
    review's, whose commit is the previous report's head; loop.md's `## Verifier brief` is appended."""
    earlier = "c" * 40
    reviews = (
        verdict_on(earlier, heading="Verifier (codex), pass 1"),
        verdict_on(earlier, heading="Verifier (codex), pass 2"),
    )
    pr = pull(body="Closes #12.\n\n## Evidence\n\nlog\n", reviews=reviews)
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.setattr(
        approvals, "merge_base", lambda base, head: asked.append((base, head)) or BASE
    )
    monkeypatch.setattr(
        approvals,
        "project",
        lambda: (
            None,
            LOOP + "\n## Verifier brief\n\n- Run the full gate bare.\n    indented snippet  \n\n",
        ),
    )
    priorities, proof, stale = tmp_path / "p.md", tmp_path / "gate.log", tmp_path / "old.log"
    priorities.write_text("- the revert path\n")
    proof.write_text(f"{HEAD}\nok\n")
    stale.write_text(f"{earlier}\nok\n")
    assert (
        approvals.main(["brief", "7", "--priorities", str(priorities), "--proof", str(proof)]) == 0
    )
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("Review PR #7 as the verifier, pass 3, following ")
    assert out[0].endswith("verifier.md.")
    assert out[1:] == [
        f"- Base: {BASE}",
        f"- Reviewed head: {HEAD}",
        "- Spec: #12",
        "- Report: tmp/loop/pr7-v3.md",
        f"- Previous report: tmp/loop/pr7-v2.md, on {earlier}: review the diff since that head and rerun its repros",
        f"- Proof log: {proof} (its first line is the head)",
        "",
        "Priorities:",
        "- the revert path",
        "",
        "- Run the full gate bare.",
        "    indented snippet  ",
    ]
    assert asked == [("main", HEAD)]
    assert approvals.main(["brief", "7", "--proof", str(proof), "--proof", str(stale)]) == 1
    assert (
        capsys.readouterr().out
        == f"PR #7: stale proof, its first line isn't the head {HEAD}: {stale}; rerun it\n"
    )
    # the first line exactly: a trailing space or a CR is not the head; a missing log is named, not a traceback
    for line in (f"{HEAD} ", f"{HEAD}\r"):
        stale.write_bytes(f"{line}\nok\n".encode())
        assert approvals.main(["brief", "7", "--proof", str(stale)]) == 1
        assert "stale proof" in capsys.readouterr().out
    assert approvals.main(["brief", "7", "--proof", str(tmp_path / "absent.log")]) == 1
    assert capsys.readouterr().out == f"PR #7: no proof log at {tmp_path / 'absent.log'}\n"
    pr["reviews"] = {"nodes": []}
    assert approvals.main(["brief", "7"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "- Report: tmp/loop/pr7-v1.md" in out
    assert not [line for line in out if line.startswith("- Previous report")]


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


def capped(*reviews: dict[str, Any], loop: str = BARE, **fields: Any) -> list[str]:
    """owner_waits on a project whose loop.md has no risk rule: only the cap asks for the owner's label."""
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
    assert approvals.cap(None) == approvals.cap(BARE) == 5  # SKILL.md § The cap
    assert approvals.cap(loop_md("loop:\n  cap: 3\n")) == 3
    with pytest.raises(approvals.Refused, match="`loop.cap` must be a whole number"):
        approvals.cap(loop_md("loop:\n  cap: 3 passes\n"))
    major = verdict_on(
        OLD, "0 blocker, 1 major, 0 minor", satisfied="no", heading="Verifier (claude), pass 3"
    )
    later = verdict_on(HEAD, heading="Verifier (claude), pass 4")
    assert capped(major, later) == []
    assert capped(major, later, loop=loop_md("loop:\n  cap: 3\n")) == [
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


BOTS = add(LOOP, "bot", 'dependabot[bot]:\n  paths:\n    - uv.lock\n    - "**/package.json"\n')
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
    assert bot(who="renovate") == UNREVIEWED  # a bot no entry names
    assert bot(kind="User") == UNREVIEWED  # a person is never the bot
    assert bot(loop=LOOP) == UNREVIEWED  # no `bot` entry: no exemption
    assert approvals.proofs("merge", made(files=()), [], BOTS) == UNREVIEWED
    assert bot(commits=("dependabot", "dependabot[bot]")) == []
    assert bot(commits=("dependabot[bot]", "worker")) == UNREVIEWED  # a person's push
    assert bot(commits=(None,)) == UNREVIEWED  # an author GitHub ties to no account
    assert bot(commits=()) == UNREVIEWED
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
    assert (
        approvals.settings(BOTS)["risk"] == approvals.settings(LOOP)["risk"]
    )  # a bot entry is no risk rule


RENOVATE = add(LOOP, "bot", "renovate:\n  branch: renovate/\n  paths:\n    - uv.lock\n")


def test_a_branch_section_exempts_an_updaters_pr_opened_under_a_persons_token() -> None:
    def made(
        branch: str = "renovate/foo",
        commits: tuple[str | None, ...] = ("writer",),
        labels: tuple[str, ...] = (),
        fork: bool = False,
        files: tuple[str, ...] = ("uv.lock",),
        author: str | None = "writer",
    ) -> dict[str, Any]:
        pr = {
            **pull(files=files, labels=labels),
            "author": author and {"__typename": "User", "login": author},
            "headRefName": branch,
            "isCrossRepository": fork,
        }
        pr["authored"] = {"nodes": [authored(by) for by in commits]}
        return pr

    def gate(loop: str = RENOVATE, **fields: Any) -> list[str]:
        return approvals.proofs("merge", made(**fields), [], loop)

    assert gate() == []  # the writer's own renovate/ branch, lock file only
    assert gate(commits=("writer", "other")) == UNREVIEWED  # a second person's commit
    assert gate(labels=("verify",)) == UNREVIEWED  # a major update asks for its review
    assert gate(branch="feature/foo") == UNREVIEWED  # another branch
    assert gate(fork=True) == UNREVIEWED  # a fork may name any branch
    assert gate(files=("uv.lock", "app.py")) == UNREVIEWED  # code needs a review as usual
    assert gate(loop=BOTS) == UNREVIEWED  # a login section never matches a person
    # a deleted author and commits mapped to no account would compare "" with "": refused
    assert gate(author=None, commits=(None,)) == UNREVIEWED


def test_the_verify_label_refuses_a_login_sections_exemption_too() -> None:
    pr = {
        **pull(files=("uv.lock",), labels=("verify",)),
        "author": {"__typename": "Bot", "login": "dependabot"},
    }
    pr["authored"] = {"nodes": [authored("dependabot[bot]")]}
    assert approvals.proofs("merge", pr, [], BOTS) == UNREVIEWED


def test_more_reviews_or_threads_than_one_page_is_refused() -> None:
    crowded = pull(reviews=(VERDICT,), threads=(True,))
    crowded["reviews"]["totalCount"] = 101
    crowded["reviewThreads"]["totalCount"] = 101
    assert approvals.proofs("merge", crowded, [approved(1, "area:web")], LOOP) == [
        "PR #7 has more than 1 reviews: the gate reads one page",
        "PR #7 has more than 1 review threads: the gate reads one page",
    ]


# --- risk rules at the merge ---

GITHUB_RULE = loop_md("risk:\n  paths:\n    - .github/**\n")


def test_a_risk_path_rule_asks_for_the_label_only_on_a_pr_touching_its_path() -> None:
    def waits(loop: str, *files: str, total: int | None = None) -> list[str]:
        pr = pull(reviews=(VERDICT,), files=files)
        if total is not None:
            pr["files"]["totalCount"] = total
        return approvals.waits(pr, [approved(1, "area:web")], loop)

    assert waits(GITHUB_RULE, ".github/ci.yml") == [GITHUB]
    assert waits(GITHUB_RULE, "README.md") == []
    # files the gate can't read
    assert waits(GITHUB_RULE, "README.md", total=101) == [
        HELD
        + "the gate can't read every file the PR changes, so the risk rule's `paths` hold until a"
        " person judges them"
    ]
    assert waits(loop_md("risk:\n  labels:\n    - area:web\n"), "README.md") == [
        HELD + "it matches a risk rule (label `area:web`)"
    ]
    assert waits(loop_md("risk:\n  labels:\n    - kind:ops\n"), "README.md") == []


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
        if args[:2] == ("api", "graphql"):
            state["calls"].append(args[:2] + args[-1:])
            return "{}"
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
    monkeypatch.setattr(approvals, "required_checks", REQUIRED)
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


def test_land_merges_a_high_risk_pr_on_a_delegated_label_into_a_feature_branch_only(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"check"})
    pr = landing["pull"]
    pr["labels"]["nodes"] += [{"name": "risk:high"}, {"name": "approved:merge"}]
    pr["timelineItems"]["nodes"].append({"createdAt": LABELED, "label": {"name": "approved:merge"}})
    pr["comments"]["nodes"].append(DELEGATED)
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (approvals.WAITING, [])
    assert "`approved:merge` is the delegated approval" in lines[-1]
    pr["baseRefName"] = "stream"
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
            {"loop": "ci: false\n"},
            (
                "PR #7: the project has no CI (loop.md `ci: false`), and no local check passed on the head"
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
        Path("docs/agents/loop.md").write_text(add(GITHUB_RULE, "loop", change.pop("loop")))
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


def test_settings_off_the_schema_are_refused_before_any_proof_and_before_ready(
    landing: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A PR the risk rule already holds never reached the cap, so `check merge` printed its proofs and passed or
    waited, and `land` marked the draft ready. The bad `cap` setting now comes first, alone, and nothing reaches GitHub.
    """
    (tmp_path / "docs" / "agents" / "loop.md").write_text(
        add(GITHUB_RULE, "loop", "cap: 3 passes\n")
    )
    refused = ["loop.md's `loop.cap` must be a whole number, not '3 passes'"]
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


def test_land_wait_reads_a_branchs_high_risk_prs_again_on_every_poll(
    landing: dict[str, Any],
    later: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A high-risk PR merged into the feature branch while its merge to main waits holds that merge for the owner."""
    landing["pull"] = proven(mergeStateStatus="UNKNOWN")
    ready = proven()
    later += [ready]
    monkeypatch.setattr(
        approvals, "merged_high", MERGED_HIGH
    )  # the real one, asking GitHub each time
    github = approvals.gh

    def gh(*args: str, data: str | None = None) -> str:
        if args[:2] == ("pr", "list"):
            return "12\n" if landing["pull"] is ready else ""
        return github(*args, data=data)

    monkeypatch.setattr(approvals, "gh", gh)
    code, lines, calls = waited(capsys, landing)
    assert (code, calls) == (approvals.WAITING, [])
    assert lines[-1] == HELD + "`risk:high` is on #12, merged into feature"


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


def test_land_wait_reads_again_a_pr_out_of_the_queue_before_github_says_merged(
    landing: dict[str, Any], later: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"] = proven("IN_PROGRESS")
    later += [
        proven("SUCCESS", isInMergeQueue=True),
        proven("SUCCESS"),  # out of the queue, not reported merged yet
        proven("SUCCESS", state="MERGED"),
    ]
    assert waited(capsys, landing) == (
        0,
        [
            f"PR #7: auto-merge on at {HEAD}, once check pass",
            f"PR #7: in the merge queue at {HEAD}",
            "PR #7 is merged",
        ],
        [(*MERGE, "--auto")],
    )


def queued(minutes: float, suites: int = 0) -> dict[str, Any]:
    """A merge-queue entry enqueued `minutes` before the clock, waiting for checks, with `suites` on its commit."""
    at = datetime.fromtimestamp(NOW - minutes * 60, UTC).isoformat().replace("+00:00", "Z")
    return {
        "state": "AWAITING_CHECKS",
        "enqueuedAt": at,
        "headCommit": {"checkSuites": {"totalCount": suites}},
    }


NOW = 1_800_000_000.0
DEQUEUED = ("api", "graphql", "id=PR_7")


def test_land_wait_dequeues_an_entry_github_never_started_checks_for_and_lands_it_again(
    landing: dict[str, Any],
    later: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(approvals.time, "time", lambda: NOW)
    landing["pull"] = proven("SUCCESS", id="PR_7", isInMergeQueue=True, mergeQueueEntry=queued(11))
    later += [
        proven("SUCCESS", id="PR_7"),  # dequeued: open, out of the queue
        proven("SUCCESS", id="PR_7", isInMergeQueue=True, mergeQueueEntry=queued(0)),
        proven("SUCCESS", id="PR_7", state="MERGED"),
    ]
    code, out, calls = waited(capsys, landing)
    assert code == 0
    assert out[0] == (
        "PR #7: its merge-queue entry waited 10 minutes for checks GitHub never started: dequeued, to land it again"
    )
    assert out[-1] == "PR #7 is merged"
    assert calls.count(DEQUEUED) == 1
    assert calls[0] == DEQUEUED and len(calls) == 2, calls


@pytest.mark.parametrize(
    "entry", [queued(11, suites=1), queued(9)], ids=["checks-started", "young"]
)
def test_land_wait_leaves_an_entry_with_a_check_suite_or_a_young_one_in_the_queue(
    entry: dict[str, Any],
    landing: dict[str, Any],
    later: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(approvals.time, "time", lambda: NOW)
    landing["pull"] = proven("SUCCESS", id="PR_7", isInMergeQueue=True, mergeQueueEntry=entry)
    later += [proven("SUCCESS", id="PR_7", state="MERGED")]
    assert waited(capsys, landing) == (
        0,
        [f"PR #7: in the merge queue at {HEAD}", "PR #7 is merged"],
        [],
    )


def test_land_without_wait_never_dequeues_a_stuck_entry(
    landing: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(approvals.time, "time", lambda: NOW)
    landing["pull"] = proven("SUCCESS", id="PR_7", isInMergeQueue=True, mergeQueueEntry=queued(60))
    assert DEQUEUED not in landed(capsys, landing)[2]


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
            add(GITHUB_RULE, "loop", "ci: false\n"),
            ("app.py",),
            (
                "PR #7: the project has no CI (loop.md `ci: false`), and no local check passed on the head"
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
SIGNED_LAND = "signed_squash_to: main\nallowed_signers: signers\n"


def sh(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def signing(landing: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """`landing` in a real checkout whose `origin` names the PR's repo and reaches a local bare repo: `main` and the
    PR's branch `feature` (also `refs/pull/7/head`) one commit ahead, an SSH signing key, and an allowed signers file
    `signers` holding it. The PR's head and verdict are the real commit; loop.md has the `land` table."""
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
    loop.write_text(add(loop.read_text(), "land", SIGNED_LAND))
    head = git("rev-parse", "feature")
    landing["pull"].update(
        headRefOid=head, reviews={"nodes": [verdict_on(head, "0 blocker, 0 major, 0 minor")]}
    )
    return {"git": git, "remote": remote, "base": git("rev-parse", "main"), "head": head}


def remote_ref(signing: dict[str, Any], ref: str) -> str:
    return sh("git", "rev-parse", ref, cwd=signing["remote"])


def test_a_hosts_global_git_config_cannot_take_over_a_tests_signing(
    signing: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host whose global config signs with a failing program still signs with the key `signing` made (#400)."""
    home = tmp_path.parent / f"{tmp_path.name}-home"
    home.mkdir()
    (home / ".gitconfig").write_text('[gpg "ssh"]\n\tprogram = false\n[commit]\n\tgpgsign = true\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    signing["git"]("commit", "-q", "-S", "--allow-empty", "-m", "signed")
    verified = subprocess.run(
        ["git", "-c", "gpg.ssh.allowedSignersFile=signers", "verify-commit", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert 'Good "git" signature for lander@example.com' in verified.stderr


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
    loop.write_text(loop.read_text().replace("  allowed_signers: signers\n", ""))
    assert refused_untouched(landing, signing, capsys) == [
        "loop.md's `land` lacks `allowed_signers`"
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

OPTED = add(LOOP, "loop", "opt_out: true\n")
OUTSIDE = (
    "PR #7 is outside the loop (loop.md `opt_out: true`, no verifier review, spec approval,"
    " revert or bot exemption): its author merges it"
)


def gate(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, list[str]]:
    code = approvals.main(list(argv))
    return code, capsys.readouterr().out.splitlines()


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
    # risk rules hold no PR outside the loop: the project accepted that with the setting
    mine["labels"]["nodes"].append({"name": "risk:high"})
    assert gate(capsys, "check", "merge", "7") == (0, [OUTSIDE])
    # without the setting, the same PR fails the gate as before
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
    assert approvals.outside(pr, add(BOTS, "loop", "opt_out: true\n")) is None
    assert approvals.outside(pr, OPTED) is not None  # no `bot` entry: a person's PR like any other


def test_a_policy_covered_spec_is_no_trail(landing: dict[str, Any]) -> None:
    mine = landing["pull"]
    mine["reviews"]["nodes"] = []
    mine["closingIssuesReferences"]["nodes"] = [
        specced(1, "kind:bug")
    ]  # `spec.auto` naming `bug` covers a bug
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
    (agents / "loop.md").write_text(loop_md("practice:\n  plan: writing-plans\n"))
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


def test_check_without_a_pr_or_an_issue_has_nothing_to_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A merge has nothing to gate before its PR; a build on a branch naming no issue is refused, since it needs an
    approved spec."""
    monkeypatch.setattr(approvals, "current_pr", lambda: None)
    monkeypatch.setattr(approvals, "git", lambda *_args: "spike\n")
    monkeypatch.chdir(PROJECT)
    assert (approvals.main(["check", "merge"]), capsys.readouterr().out) == (
        0,
        "no PR for this branch yet: nothing to gate\n",
    )
    assert (approvals.main(["check", "build"]), capsys.readouterr().out) == (
        1,
        (
            "no PR for this branch yet, and its name holds no issue number: pass --issue <n>, since a build needs an"
            " approved spec\n"
        ),
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
        loop_md('components:\n  billing: invoices.\ncategories:\n  research: ""\n')
    )
    (agents / "loop.md").write_text(BARE)
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
                f"From the recorded run at {record['time']}, not run again.\n"
            ),
        )
    ]
    posted = [body for kind, _pr, body in github if kind == "comment"]
    merged = pull(reviews=(VERDICT,), comments=tuple(posted), labels=OWNED, checks=())
    assert merge(merged, [approved(1, "area:web")], add(LOOP, "loop", "ci: false\n")) == []


def test_a_local_ci_comment_names_no_host(
    checkout: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run and recorded on a host named for its owner, the pass is posted without it, and still proves the head."""
    sent = posts(monkeypatch)
    assert approvals.main(["local-ci", "--record"]) == 0
    record = json.loads(approvals.recorded(HEAD).read_text())
    assert record["host"] == "owner-MacBook.local"  # the local record keeps it
    assert approvals.main(["local-ci", "7"]) == 0
    [body] = sent
    assert "owner-MacBook" not in body and "/Users/owner" not in body
    merged = pull(reviews=(VERDICT,), comments=(body,), labels=OWNED, checks=())
    assert merge(merged, [approved(1, "area:web")], add(LOOP, "loop", "ci: false\n")) == []


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


ENV_LOOP = add(LOOP, "loop", "local_ci_env:\n  - GATE_UI_TESTS\n  - GATE_SCOPE\n")


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
                f"From the recorded run at {record['time']}, not run again.\n"
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


@pytest.mark.parametrize("names", ["\n  - GATE-UI", "\n  - GATE_UI GATE_SCOPE"])
def test_a_local_ci_env_that_is_no_list_of_variable_names_is_refused(
    github: list[tuple[Any, ...]],
    checkout: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    names: str,
) -> None:
    checkout["loop"] = add(LOOP, "loop", f"local_ci_env:{names}\n")
    assert approvals.main(["local-ci", "7"]) == 1
    assert (checkout["runs"], github) == (0, [])
    assert "`local_ci_env`" in capsys.readouterr().out


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
    assert merge(merged, [approved(1, "area:web")], add(LOOP, "loop", "ci: false\n")) == []


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

POLICY = loop_md(
    "spec:\n  auto:\n    - bug\n    - follow-up\n    - sub-issue\nrisk:\n  paths:\n    - billing/**\n"
)
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
    assert approvals.spec_policy(spec, set(approvals.SPEC_KINDS)) is covered
    assert not approvals.spec_policy(spec, set())
    assert "parent {" in approvals.ISSUE and "author { login }" in approvals.ISSUE


def test_spec_policy_covers_only_the_kinds_auto_names(writers: list[str]) -> None:
    bug, follow_up = issue(1, "kind:bug"), issue(2, "kind:enhancement", body="Found while #12\n")
    child = story(epic("approved:spec"))
    for kind, covered in (("bug", bug), ("follow-up", follow_up), ("sub-issue", child)):
        assert [approvals.spec_policy(spec, {kind}) for spec in (bug, follow_up, child)] == [
            spec is covered for spec in (bug, follow_up, child)
        ]
    assert approvals.spec_kinds(loop_md("spec:\n  auto:\n    - bug\n")) == {"bug"}
    assert approvals.spec_kinds(AUTO) == approvals.spec_kinds(BARE) == set()


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
    # without the policy, a bug is the owner's to approve like any spec
    assert approvals.proofs(
        "build", pull(), [bug], loop_md("risk:\n  paths:\n    - billing/**\n")
    ) == [
        "#1 has no `Approved: spec` record by the owner",
        "#1 lacks the `approved:spec` label",
    ]
    assert problems([specced(1, "kind:bug", "needs-owner")]) == [
        "#1 waits for the owner (needs-owner)"
    ]


AUTO = loop_md(
    "spec:\n  auto: true\nrisk:\n  labels:\n    - area:api\n  paths:\n    - billing/**\n"
)


def by(author: str, found: dict[str, Any]) -> dict[str, Any]:
    return {**found, "author": {"login": author}}


def test_check_build_before_the_pr_judges_the_files_the_branch_changed(
    writers: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no PR, a `paths` risk rule under `spec.auto` reads the files the branch changed since it left the default
    branch, as it reads a PR's: a protected file holds the spec for the owner, and files git can't list hold too."""
    spec = {
        1: by("worker", specced(1, "kind:enhancement")),
        2: by("worker", approved(2, "kind:enhancement", "area:web", "size:S")),
    }
    changed: list[str | None] = [""]

    def git(*args: str) -> str:
        if args[0] == "diff":
            assert args == ("diff", "--name-only", "-z", "origin/main...HEAD")
            if changed[0] is None:
                raise subprocess.CalledProcessError(128, ["git", *args])
            return "".join(f"{path}\0" for path in changed[0].split())
        return "origin/main\n" if args[-1] == "origin/HEAD" else "loop/1-fix\n"

    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, AUTO))
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    monkeypatch.setattr(approvals, "issue_node", lambda n: spec[n])
    monkeypatch.setattr(approvals, "current_pr", lambda: None)
    monkeypatch.setattr(approvals, "git", git)

    def build(number: int) -> tuple[int, list[str]]:
        code = approvals.main(["check", "build", "--issue", str(number)])
        return code, capsys.readouterr().out.splitlines()

    assert build(1) == (0, ["#1: every build proof holds; no PR yet"])
    changed[0] = "app.py\nbilling/a.py\n"
    assert build(1) == (
        1,
        [
            (
                "#1: its spec is the owner's to approve under `spec.auto: true`, since it matches a risk rule (path"
                " `billing/**`)"
            ),
            "#1 has no `Approved: spec` record by the owner",
            "#1 lacks the `approved:spec` label",
        ],
    )
    assert build(2)[0] == 0  # the owner approved it
    changed[0] = None
    code, out = build(1)
    assert code == 1 and "the gate can't read every file the PR changes" in out[0]


def test_the_branch_files_check_build_reads_are_its_real_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-ASCII name, which git quotes in its plain output, and one with spaces reach the risk rules as committed."""
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    committed(clone)
    git_in(clone, "branch", "-M", "main")
    git_in(clone, "remote", "add", "origin", str(origin))
    git_in(clone, "push", "-q", "origin", "main")
    git_in(clone, "remote", "set-head", "origin", "main")
    git_in(clone, "checkout", "-q", "-b", "loop/1-fix")
    names = [".github/workflows/contrôle.yml", "docs/decision notes.md"]
    for name in names:
        (clone / name).parent.mkdir(parents=True, exist_ok=True)
        (clone / name).write_text("x\n")
    git_in(clone, "add", "-A")
    git_in(clone, "commit", "-qm", "files")
    monkeypatch.chdir(clone)
    assert sorted(approvals.paths(approvals.unopened())) == sorted(names)


def test_spec_auto_is_its_own_policy() -> None:
    assert approvals.spec_auto(AUTO) and not approvals.spec_auto(POLICY)
    assert not approvals.spec_auto(loop_md("spec:\n  auto: false\n")) and not approvals.spec_auto(
        BARE
    )


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
        "#4: its spec is the owner's to approve under `spec.auto: true`, since it matches a risk rule (label `area:api`)",
        "#6: its spec is the owner's to approve under `spec.auto: true`, since its author @drive-by can't write to the repo",
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
        "#1: its spec is the owner's to approve under `spec.auto: true`, since it matches a risk rule (path `billing/**`)"
    ]
    assert approvals.proofs("build", pushed, [feature], AUTO) == [
        "#1 has no `Approved: spec` record by the owner",
        "#1 lacks the `approved:spec` label",
    ]
    # a PR label counts too, and paths the gate can't judge hold
    assert approvals.holds(pull(labels=("area:api",)), [feature], AUTO)
    crowded = pull()
    crowded["files"]["totalCount"] = 101
    assert approvals.holds(crowded, [feature], AUTO) == [
        (
            "#1: its spec is the owner's to approve under `spec.auto: true`, since the gate can't read every file"
            " the PR changes, so the risk rule's `paths` hold until a person judges them"
        )
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
    # the same PR beside `spec.auto` as a list waits for the owner's merge label
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
        ((), ("size:XL",), ("app.py",), "it matches a risk rule (label `size:XL`)"),
    ],
    ids=["label-on-the-pr", "label-on-its-issue", "risk-path", "risk-label"],
)
def test_a_high_risk_merge_waits_for_the_owner_and_says_why(
    labels: tuple[str, ...], issue_labels: tuple[str, ...], files: tuple[str, ...], why: str
) -> None:
    loop = loop_md(
        "spec:\n  auto:\n    - bug\n    - follow-up\n    - sub-issue\nrisk:\n  labels:\n    - size:L\n    - size:XL\n    - area:api\n  paths:\n    - billing/**\n"
    )
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
DEMO = SCRIPTS.parent.parent / "demo" / "scripts" / "demo.sh"


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
    demo.sh refuse, naming them, before any gh call but demo.sh's version check."""
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
    # demo.sh: a gh that passes the version check and exits 77 on any other call shows whether the
    # guard let it through
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "gh").write_text(
        '#!/bin/sh\n[ "$1" = --version ] && echo "gh version 2.103.3" && exit 0\nexit 77\n'
    )
    (shim / "gh").chmod(0o755)
    (tmp_path / "v.mp4").write_bytes(b"x")
    shell = subprocess.run(
        ["bash", str(DEMO), "v.mp4"],
        capture_output=True,
        text=True,
        env={"PATH": f"{shim}:/usr/bin:/bin", "HOME": str(tmp_path)},
        check=False,
    )
    assert (shell.returncode, "me/fork them/fork" in shell.stderr) == (
        (1, True) if refused else (77, False)
    )


# --- the verifier judges risk (`verifier: true`) ---


VERIFIED = loop_md(
    "spec:\n  auto:\n    - bug\n    - follow-up\n    - sub-issue\nrisk:\n  verifier: true\n"
)


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
    loop = loop_md(
        "spec:\n  auto:\n    - bug\n    - follow-up\n    - sub-issue\nrisk:\n  verifier: true\n  paths:\n    - .github/**\n"
    )
    pr = pull(reviews=(judging("low — a workflow comment"),), files=(".github/ci.yml",))
    issues = [approved(1, "area:web", "kind:enhancement")]
    assert merge(pr, issues, loop) == [HELD + "it matches a risk rule (path `.github/**`)"]
    assert merge({**pr, "files": {"nodes": [{"path": "app.py"}]}}, issues, loop) == []


@pytest.mark.parametrize("spec", ["", "  auto: true\n"], ids=["merge", "spec-auto"])
@pytest.mark.parametrize(
    "condition",
    [
        "  paths:\n    - docs/verifier.md",
        "  paths:\n    - verifier/**",
        "  labels:\n    - area:verifier",
    ],
)
def test_the_word_verifier_in_a_path_or_label_is_no_verifier_term(
    spec: str, condition: str
) -> None:
    """A rule without the `verifier` term holds as it did before it: the verifier's `Risk:` line, high or missing,
    holds nothing."""
    loop = loop_md(f"spec:\n{spec}risk:\n{condition}\n")
    issues = [approved(1, "area:web", "kind:enhancement")]
    for review in (judging("high — a gate changed"), judging(None)):
        assert approvals.risk(pull(reviews=(review,), files=("app.py",)), issues, loop) is None


def test_under_spec_auto_the_verifier_term_holds_the_merge_not_the_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(approvals, "writer", lambda login: True)
    loop = loop_md("spec:\n  auto: true\nrisk:\n  verifier: true\n  paths:\n    - billing/**\n")
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


@pytest.mark.parametrize(
    ("change", "why"),
    [
        (("", ""), None),
        (
            ("Risk: low — a test fixture\n", ""),
            "has no `Risk: low|high — <reason>` line: the report is unfinished",
        ),
        (
            ("SATISFIED: no\n", ""),
            "has no `VERDICT:` or `SATISFIED:` line: the report is unfinished",
        ),
        (
            ("Verifier: claude, same-family, pass 2\n", ""),
            "has no `Verifier: <family>, pass <n>` line",
        ),
    ],
)
def test_report_reads_a_report_as_verdict_would_without_github(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    change: tuple[str, str],
    why: str | None,
) -> None:
    """The verifier runs it before replying, in a sandbox with no GitHub, so a format slip costs no extra turn."""

    def offline(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"report reached out: {args}")

    monkeypatch.setattr(approvals, "gh", offline)
    monkeypatch.setattr(approvals, "one_repo", offline)
    report = tmp_path / "report.md"
    report.write_text(REPORT.replace(*change) if change[0] else REPORT)
    assert approvals.main(["report", str(report)]) == (1 if why else 0)
    assert capsys.readouterr().out == (
        f"{report} {why}\n" if why else f"{report} reads as a verdict\n"
    )


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


def batch_note(head: str, merge: str, batch: str, exit: int = 0, env: str = "default") -> str:
    return (
        f"{approvals.BATCHED}\nHead: {head}\nMerge: {merge}\nBatch: {batch}\nExit: {exit}\nEnv: {env}\n"
        "Gated: 2026-01-01T00:00:00Z\nLog: /tmp/gate.log\n"
    )


def gated_head(head: str, env: dict[str, str | None] | None = None) -> None:
    """Record a green `local-ci --record` pass on `head`, as run_local_ci() writes it."""
    where = approvals.recorded(head)
    where.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "head": head,
        "command": " ".join(approvals.LOCAL_CI),
        "exit": 0,
        "env": {} if env is None else env,
        "time": "2026-01-01T00:00:00Z",
        "host": "host",
    }
    where.write_text(json.dumps(record))


NO_LOCAL_CHECK = "PR #7: the project has no CI (loop.md `ci: false`), and no local check passed on the head (approvals.py local-ci)"


QUEUED = add(
    LOOP, "loop", "batch_queue: true\n"
)  # a project that lands through a batching merge queue


def test_a_batch_proof_counts_only_where_loop_md_opts_into_a_queue(batched: dict[str, str]) -> None:
    """A project that never set up a batching merge queue gets no second way past the CI or local-check wait: the
    same valid batch proof stands in for it only under `batch_queue: true`."""
    gated_head(batched["head"])
    proof = batch_note(batched["head"], batched["merge"], batched["batch"])
    assert queued_merge(batched["head"], proof) == []
    pr = pull(reviews=(verdict_on(batched["head"]),), comments=(proof,), checks=())
    pr["headRefOid"] = batched["head"]
    assert merge(pr, [approved(1, "area:web")], add(LOOP, "loop", "ci: false\n")) == [
        NO_LOCAL_CHECK
    ]
    assert merge(pr, [approved(1, "area:web")]) == ["PR #7: no `check` on the head commit yet"]


def queued_merge(head: str, *comments: str) -> list[str]:
    pr = pull(reviews=(verdict_on(head),), comments=comments, checks=())
    pr["headRefOid"] = head
    return merge(pr, [approved(1, "area:web")], add(LOOP, "loop", "ci: false\nbatch_queue: true\n"))


def queued_reasons(head: str, *comments: str) -> list[str] | None:
    pr = pull(reviews=(verdict_on(head),), comments=comments, checks=())
    pr["headRefOid"] = head
    return approvals.queued(pr)


def test_a_green_batch_that_merged_the_head_cleanly_is_its_merge_proof(
    batched: dict[str, str],
) -> None:
    head, merged, batch = batched["head"], batched["merge"], batched["batch"]
    gated_head(head)
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
    gated_head(head)
    fields = {"merge": batched["merge"], "batch": batched["batch"], "exit": 0}
    fields.update(
        {key: batched.get(value, value) for key, value in change.items() if key != "exit"}
    )
    fields["exit"] = change.get("exit", 0)
    names = {**batched, "fff": "f" * 40}
    proof = batch_note(head, fields["merge"], fields["batch"], fields["exit"])
    # it adds no hold of its own: the wait is the one a PR with no batch proof has
    assert queued_merge(head, proof) == [NO_LOCAL_CHECK]
    assert queued_reasons(head, proof) == [f"PR #7: {said.format(**names)}"]


def test_a_batch_cannot_stand_in_for_the_heads_own_gate(
    batched: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    head, merged, batch = batched["head"], batched["merge"], batched["batch"]
    note = batch_note(head, merged, batch)
    ungated = f"PR #7: the head {head} has no green `local-ci --record` pass of its own under this environment, which a batch never stands in for"
    assert queued_merge(head, note) == [NO_LOCAL_CHECK]
    assert queued_reasons(head, note) == [ungated]
    gated_head(head, {"GATE_UI_TESTS": "smoke"})  # gated, but under another env than this one
    assert queued_merge(head, note) == [NO_LOCAL_CHECK]
    assert queued_reasons(head, note) == [ungated]
    monkeypatch.setattr(approvals, "local_ci_env", lambda: {"GATE_UI_TESTS": "smoke"})
    assert queued_merge(head, note) == [NO_LOCAL_CHECK]
    assert queued_reasons(head, note) == [
        f"PR #7: batch {batch} names the head's gate env `default`, its record `GATE_UI_TESTS=smoke`",
    ]
    assert queued_merge(head, batch_note(head, merged, batch, env="GATE_UI_TESTS=smoke")) == []


def test_no_batch_comment_or_one_for_another_head_leaves_the_wait(batched: dict[str, str]) -> None:
    head = batched["head"]
    gated_head(head)
    assert queued_merge(head) == [NO_LOCAL_CHECK]
    assert queued_merge(head, batch_note("b" * 40, batched["merge"], batched["batch"])) == [
        NO_LOCAL_CHECK
    ]
    assert queued_merge(head, "> " + batch_note(head, batched["merge"], batched["batch"])) == [
        NO_LOCAL_CHECK
    ]


def test_only_a_batch_proof_by_the_running_account_or_a_writer_counts(
    batched: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    head = batched["head"]
    gated_head(head)
    proof = note(batch_note(head, batched["merge"], batched["batch"]), author={"login": "stranger"})
    monkeypatch.setattr(approvals, "writer", lambda login: login == "colleague")
    pr = pull(reviews=(verdict_on(head),), comments=(proof,), checks=())
    pr["headRefOid"] = head
    lines = merge(pr, [approved(1, "area:web")], QUEUED)
    assert lines and all("batch" not in line for line in lines)  # waits on CI, as with no proof
    proof["author"] = {"login": "colleague"}
    assert merge(pr, [approved(1, "area:web")], QUEUED) == []
    proof["author"] = None  # a deleted account
    assert merge(pr, [approved(1, "area:web")], QUEUED) == lines


def test_comments_that_are_no_batch_proof_cost_no_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    """ran() runs on every check merge and land poll: other comments mustn't each cost a GitHub call."""
    asked: list[str | None] = []
    monkeypatch.setattr(approvals, "writer", lambda login: asked.append(login) or False)
    monkeypatch.setattr(approvals, "viewer", lambda: asked.append(None) or "loop")
    comments = [note(f"review note {n}", author={"login": "some-bot"}) for n in range(20)]
    approvals.ran(pull(reviews=(VERDICT,), comments=comments), None)
    assert asked == []


RED_BATCH = batch_note(HEAD, "c" * 40, "d" * 40, exit=1)


def test_a_red_batch_through_another_pr_leaves_check_merge_on_green_ci() -> None:
    assert merge(pull(reviews=(VERDICT,), comments=(RED_BATCH,)), [approved(1, "area:web")]) == []


def test_a_red_batch_through_another_pr_leaves_land_alone(
    landing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    landing["pull"]["comments"]["nodes"].append(note(RED_BATCH))
    code, lines, calls = landed(capsys, landing)
    assert (code, calls) == (0, [MERGE]), lines


def test_a_head_evicted_through_another_pr_may_re_enter_the_queue(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    (Path.cwd() / "docs" / "agents" / "loop.md").write_text(
        add(GITHUB_RULE, "loop", "batch_queue: true\n")
    )
    queueing["pull"]["comments"]["nodes"].append(note(RED_BATCH))
    assert queue_check(capsys) == (0, [f"PR #7 may enter a merge queue at {HEAD}"])


def test_with_ci_check_queue_still_needs_the_heads_own_record(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """batch refuses a head without one, so a head check queue admitted would never get its proof."""
    (Path.cwd() / "docs" / "agents" / "loop.md").write_text(
        add(GITHUB_RULE, "loop", "batch_queue: true\n")
    )
    queueing["records"] = set()
    assert queue_check(capsys) == (
        1,
        [
            f"PR #7: no `local-ci --record` pass on {HEAD} under this environment (approvals.py local-ci --record)"
        ],
    )


def test_the_batch_proof_also_stands_in_for_ci(batched: dict[str, str]) -> None:
    head = batched["head"]
    gated_head(head)
    pr = pull(
        reviews=(verdict_on(head),),
        comments=(batch_note(head, batched["merge"], batched["batch"]),),
        checks=(),
    )
    pr["headRefOid"] = head
    assert merge(pr, [approved(1, "area:web")], QUEUED) == []


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
    assert approvals.main(args) == 1  # the head has no pass of its own
    assert posted == []
    gated_head(batched["head"])
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


def posts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every body comment() hands gh, from a fake host whose name and home name its owner."""
    sent: list[str] = []
    monkeypatch.setattr(approvals, "comment", COMMENT)
    monkeypatch.setattr(approvals, "gh", lambda *args, data=None: sent.append(data) or "")
    monkeypatch.setattr(approvals.socket, "gethostname", lambda: "owner-MacBook.local")
    monkeypatch.setenv("HOME", "/Users/owner")
    return sent


def test_posted_comments_name_no_host_or_home(
    batched: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A queue gate comment quoting build notes under the home directory, from a host named for its owner."""
    sent = posts(monkeypatch)
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    # a gate env naming a path under the home directory, posted as `~` and still matching the head's record
    env = {"CACHE": "/Users/owner/cache"}
    monkeypatch.setattr(approvals, "local_ci_env", lambda: env)
    gated_head(batched["head"], env)
    record = approvals.recorded(batched["head"])
    record.write_text(record.read_text().replace('"host": "host"', '"host": "owner-MacBook.local"'))
    log = tmp_path / "gate.log"
    log.write_text(
        "note: cached at /Users/owner/Library/Caches/x\nhome /Users/owner\ngate: green\n"
    )
    args = ["batch", "7", "--merge", batched["merge"], "--batch", batched["batch"], "--exit", "0"]
    assert approvals.main([*args, "--log", str(log)]) == 0
    [body] = sent
    assert "owner-MacBook" not in body and "/Users/owner" not in body
    assert "note: cached at ~/Library/Caches/x\nhome ~\n" in body and "Env: CACHE=~/cache\n" in body
    assert queued_merge(batched["head"], body) == []


def test_a_posted_review_names_no_home_however_it_is_spelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A review goes as JSON: a non-ASCII home is replaced as GitHub decodes it, in the body and inline comments."""
    sent = posts(monkeypatch)
    monkeypatch.setenv("HOME", "/home/é")
    approvals.post_review(
        7,
        {
            "body": "cache /home/é/cache",
            "comments": [{"path": "a.py", "line": 1, "body": "at /home/é"}],
        },
    )
    review = json.loads(sent[0])
    assert (review["body"], review["comments"][0]["body"]) == ("cache ~/cache", "at ~")


@pytest.fixture
def queueing(landing: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """`landing` with `ci: false`, and a local-ci pass recorded on HEAD under the current env."""
    (Path.cwd() / "docs" / "agents" / "loop.md").write_text(
        add(GITHUB_RULE, "loop", "ci: false\nbatch_queue: true\n")
    )
    landing["records"] = {HEAD}
    monkeypatch.setattr(
        approvals, "reusable", lambda head: {"head": head} if head in landing["records"] else None
    )
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    return landing


def queue_check(capsys: pytest.CaptureFixture[str], head: str = HEAD) -> tuple[int, list[str]]:
    code = approvals.main(["check", "queue", "7", "--head", head])
    return code, capsys.readouterr().out.splitlines()


def test_check_queue_refuses_a_project_without_the_setting(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    (Path.cwd() / "docs" / "agents" / "loop.md").write_text(add(GITHUB_RULE, "loop", "ci: false\n"))
    assert queue_check(capsys) == (
        1,
        [
            (
                "PR #7: loop.md doesn't opt into a batching merge queue (`batch_queue: true` under `loop`), so it lands"
                " through `land`"
            )
        ],
    )


def test_check_queue_waits_for_the_checks_the_base_branch_requires(
    queueing: dict[str, Any], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (Path.cwd() / "docs" / "agents" / "loop.md").write_text(
        add(GITHUB_RULE, "loop", "batch_queue: true\n")
    )
    monkeypatch.setattr(
        approvals, "required_checks", lambda _base: {"qualify", approvals.APPROVALS}
    )
    assert queue_check(capsys) == (1, ["PR #7: no `qualify` on the head commit yet"])


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
    (Path.cwd() / "docs" / "agents" / "loop.md").write_text(
        add(GITHUB_RULE, "loop", "batch_queue: true\n")
    )
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


# --- a clean merge of main carries the head's verdict, never its local-ci record, where loop.md's carry_over_main says so ---

NO_CI = add(LOOP, "loop", "ci: false\n")
CARRY = add(NO_CI, "carry_over_main", "except:\n  - mise.toml\n")
APP = "".join(f"line {n}\n" for n in range(1, 11))


def carries(merge: str, head: str, base: str, since: str, branch: str = "main") -> str:
    return (
        f"{merge} carries the proofs of {head}: it is the clean merge (git merge-tree) of {head} and {branch}'s"
        f" {base}, whose changes since {since} touch none of the PR's files, and neither side touches a"
        " `carry_over_main.except` path"
    )


@pytest.fixture
def carrying(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., dict[str, str]]:
    """A bare `origin` whose `main` holds app.py and mise.toml, and the PR's head `feature` (`head`), which changes
    app.py's first line. `merged(files)` commits `files` on a branch off that `main` (`base`) and merges it into the
    head as git would (`merge`, the head its first parent): `resolve` writes what a conflict leaves, `extra` adds a
    file the merge alone has, `crossed` first has each side merge the other's commit (a criss-cross, so the head is
    that merge and the two have two merge bases). The test runs in a clone made before any of them was pushed, so
    the gate must fetch."""
    origin, work, checker = (tmp_path / name for name in ("origin.git", "work", "checker"))
    sh("git", "init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    sh("git", "clone", "-q", str(origin), str(work), cwd=tmp_path)
    who = ("-c", "commit.gpgsign=false", "-c", "user.name=Lead", "-c", "user.email=l@example.com")
    git = lambda *args: sh("git", *who, *args, cwd=work)

    def write(files: dict[str, str]) -> None:
        for name, text in files.items():
            (work / name).write_text(text)
        git("add", "-A")

    write({"app.py": APP, "mise.toml": "[tools]\n"})
    git("commit", "-qm", "base")
    git("branch", "-M", "main")
    git("push", "-q", "origin", "HEAD:main")
    sh("git", "clone", "-q", str(origin), str(checker), cwd=tmp_path)
    git("switch", "-qc", "feature")
    write({"app.py": APP.replace("line 1\n", "line 1, the feature\n")})
    git("commit", "-qm", "feature")
    head = git("rev-parse", "HEAD")
    cases = itertools.count()

    def merged(
        files: dict[str, str],
        resolve: dict[str, str] | None = None,
        extra: dict[str, str] | None = None,
        crossed: bool = False,
    ) -> dict[str, str]:
        n = next(cases)
        git("switch", "-qc", f"base{n}", "main")
        write(files)
        git("commit", "-qm", f"main moved {n}")
        first = head
        if crossed:
            moved = git("rev-parse", "HEAD")
            git("merge", "-q", "--no-ff", "-m", f"main takes the feature {n}", head)
            git("switch", "-q", "--detach", head)
            git("merge", "-q", "--no-ff", "-m", f"the feature takes main {n}", moved)
            first = git("rev-parse", "HEAD")
            git("switch", "-q", f"base{n}")
        base = git("rev-parse", "HEAD")
        git("switch", "-q", "--detach", first)
        subprocess.run(
            ["git", *who, "merge", "-q", "--no-ff", "--no-commit", base],
            cwd=work,
            capture_output=True,
            check=False,
        )
        write({**(resolve or {}), **(extra or {})})
        git("commit", "-qm", f"Merge main {n}")
        merge = git("rev-parse", "HEAD")
        git(
            "push",
            "-q",
            "origin",
            f"{head}:refs/heads/feature",
            f"{base}:refs/heads/main{n}",
            f"{merge}:refs/heads/pr{n}",
        )
        return {"head": first, "base": base, "merge": merge, "since": git("rev-parse", "main")}

    monkeypatch.chdir(checker)
    return merged


def carried_pull(case: dict[str, str], *comments: str, risk: str = "") -> dict[str, Any]:
    """The PR whose head is the merge, with a satisfied verdict on the head it merged main into."""
    review = verdict_on(case["head"])
    review["body"] += risk
    pr = pull(reviews=(review,), comments=comments, checks=(), files=("app.py",))
    pr.update(headRefOid=case["merge"], baseRefOid=case["base"])
    return pr


@pytest.fixture
def posting(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """`local-ci <pr>` against a stubbed GitHub: `pull` is the PR, `loop` loop.md; `posted` holds each comment and
    `ran` each head the check would run on, which it never does here."""
    state: dict[str, Any] = {"posted": [], "ran": [], "loop": CARRY}

    def run_local_ci(pr: int | None, head: str | None) -> dict[str, Any]:
        state["ran"].append(head)
        raise approvals.Refused("the check would run")

    monkeypatch.setattr(approvals, "comment", lambda _number, body: state["posted"].append(body))
    monkeypatch.setattr(approvals, "pull_request", lambda _n: state["pull"])
    monkeypatch.setattr(approvals, "project", lambda: (None, state["loop"]))
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    monkeypatch.setattr(approvals, "run_local_ci", run_local_ci)
    return state


def test_a_clean_merge_of_main_carries_the_verdict_but_never_the_local_ci_record(
    carrying: Callable[..., dict[str, str]],
    posting: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Under `ci: false` the merge reruns its own gate, as CI would: the head's record stays the head's."""
    case = carrying({"other.txt": "main moved\n"})
    head, merge_sha = case["head"], case["merge"]
    gated_head(head)
    posting["pull"] = carried_pull(case)
    assert approvals.main(["local-ci", "7"]) == 1
    assert (posting["ran"], posting["posted"]) == ([merge_sha], [])
    capsys.readouterr()
    on_head = f"{approvals.CHECKED}\nHead: {head}\nCommand: mise run check:all\nEnv: default\n"
    assert merge(carried_pull(case, on_head), [approved(1, "area:web")], CARRY) == [NO_LOCAL_CHECK]
    assert capsys.readouterr().out.splitlines() == [
        f"PR #7: {carries(merge_sha, head, case['base'], case['since'])}"
    ]


def test_a_carried_verdicts_risk_line_still_holds_the_merge(
    carrying: Callable[..., dict[str, str]],
) -> None:
    case = carrying({"other.txt": "main moved\n"})
    pr = carried_pull(case, risk="Risk: high — a test fixture\n")
    assert approvals.risk(pr, [], add(CARRY, "risk", "verifier: true\n")) == (
        f"it matches a risk rule (verifier): the verifier's pass 1 on {case['head'][:7]} says"
        " `Risk: high — a test fixture`"
    )


CONFLICTED = APP.replace("line 1\n", "line 1, on main\n")
REFUSED = {
    "a resolved conflict": (
        {"app.py": CONFLICTED},
        {"resolve": {"app.py": APP.replace("line 1\n", "line 1, both\n")}},
        CARRY,
        "{head} and {base} conflict",
    ),
    "an evil merge": (
        {"other.txt": "main moved\n"},
        {"extra": {"extra.txt": "in neither parent\n"}},
        CARRY,
        "{merge}'s tree is not git merge-tree's of its parents: the merge resolved or added something",
    ),
    "an overlapping file": (
        {"app.py": APP.replace("line 10\n", "line 10, on main\n")},
        {},
        CARRY,
        "app.py changed on both sides since {since}",
    ),
    "a touched except-path": (
        {"mise.toml": "[tools]\nuv = 'latest'\n"},
        {},
        CARRY,
        "main's changes since {since} touch mise.toml, a `carry_over_main.except` path",
    ),
    "the PR's own except-path change": (
        {"other.txt": "main moved\n"},
        {},
        add(NO_CI, "carry_over_main", "except:\n  - '*.py'\n"),
        "the PR's changes since {since} touch app.py, a `carry_over_main.except` path",
    ),
    "a criss-cross merge": (
        {"other.txt": "main moved\n"},
        {"crossed": True},
        CARRY,
        "{head} and {base} have 2 merge bases",
    ),
    "a project without the line": ({"other.txt": "main moved\n"}, {}, NO_CI, None),
}


def test_a_submodule_bump_main_hides_with_ignore_all_still_meets_the_except_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ignore = all` in .gitmodules hides a submodule's bump from a plain git diff."""
    who = ("-c", "commit.gpgsign=false", "-c", "user.name=Lead", "-c", "user.email=l@example.com")
    git = lambda *args: sh("git", *who, *args, cwd=tmp_path)
    git("init", "-q", "-b", "main")

    def commit(text: str) -> None:
        (tmp_path / "app").write_text(text)
        git("add", "-A")
        git("commit", "-qm", text)

    commit("lib 1\n")
    lib1 = git("rev-parse", "HEAD")
    commit("lib 2\n")
    lib2 = git("rev-parse", "HEAD")
    (tmp_path / ".gitmodules").write_text(
        '[submodule "deps/lib"]\n\tpath = deps/lib\n\turl = ./lib\n\tignore = all\n'
    )
    (tmp_path / "deps" / "lib").mkdir(parents=True)
    git("update-index", "--add", "--cacheinfo", f"160000,{lib1},deps/lib")
    commit("base\n")
    git("switch", "-qc", "feature")
    commit("feature\n")
    head = git("rev-parse", "HEAD")
    git("switch", "-q", "main")
    git("update-index", "--cacheinfo", f"160000,{lib2},deps/lib")
    git("commit", "-qm", "main bumps the dependency")
    tip = git("rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    why = approvals.merged(head, tip, ["deps/**"], "main")
    assert isinstance(why, str) and why.endswith("touch deps/lib, a `carry_over_main.except` path")


def test_diff_relative_run_from_a_subdirectory_still_meets_the_except_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`diff.relative` makes a porcelain diff drop what lies outside the current directory."""
    who = ("-c", "commit.gpgsign=false", "-c", "user.name=Lead", "-c", "user.email=l@example.com")
    git = lambda *args: sh("git", *who, *args, cwd=tmp_path)
    git("init", "-q", "-b", "main")
    git("config", "diff.relative", "true")
    (tmp_path / "pkg").mkdir()

    def commit(files: dict[str, str]) -> str:
        for name, text in files.items():
            (tmp_path / name).write_text(text)
        git("add", "-A")
        git("commit", "-qm", "commit")
        return git("rev-parse", "HEAD")

    commit({"guard.cfg": "a\n", "pkg/feature": "a\n"})
    git("switch", "-qc", "feature")
    head = commit({"pkg/feature": "b\n"})
    git("switch", "-q", "main")
    tip = commit({"guard.cfg": "b\n"})
    monkeypatch.chdir(tmp_path / "pkg")
    why = approvals.merged(head, tip, ["guard.cfg"], "main")
    assert isinstance(why, str) and why.endswith("touch guard.cfg, a `carry_over_main.except` path")


@pytest.mark.parametrize(("files", "merging", "loop", "why"), REFUSED.values(), ids=REFUSED.keys())
def test_a_merge_that_may_have_changed_the_prs_code_carries_nothing(
    carrying: Callable[..., dict[str, str]],
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    merging: dict[str, Any],
    loop: str,
    why: str | None,
) -> None:
    """Each falls back to today's proofs: a verifier pass on the merge."""
    case = carrying(files, **merging)
    head, merge_sha = case["head"], case["merge"]
    assert merge(carried_pull(case), [approved(1, "area:web")], loop) == [
        (
            f"PR #7: the newest verifier review is on {head}, not on the head {merge_sha}:"
            " every commit after a verdict needs a verdict of its own"
        ),
        NO_LOCAL_CHECK,
    ]
    said = (
        []
        if why is None
        else [f"PR #7: {merge_sha} carries nothing from {head}: {why.format(**case)}"]
    )
    assert capsys.readouterr().out.splitlines() == said


def test_without_the_line_check_merge_and_land_read_no_git(
    carrying: Callable[..., dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A project without carry_over_main gates exactly as before: nothing runs git to look for a carry."""
    case = carrying({"other.txt": "main moved\n"})
    monkeypatch.setattr(approvals, "git", lambda *args: pytest.fail(f"git {args}"))
    monkeypatch.setattr(approvals, "fetched", lambda sha: pytest.fail(f"fetched {sha}"))
    pr = carried_pull(case)
    assert approvals.judged(pr, NO_CI) is None
    assert merge(pr, [approved(1, "area:web")], NO_CI)[0].startswith(
        "PR #7: the newest verifier review is on"
    )
    assert capsys.readouterr().out == ""


def test_a_merge_of_a_commit_not_on_the_base_carries_nothing(
    carrying: Callable[..., dict[str, str]], capsys: pytest.CaptureFixture[str]
) -> None:
    """Another branch merged in is no merge of main, however disjoint: main's tip here never reached it."""
    case = carrying({"other.txt": "not on main\n"})
    pr = carried_pull(case)
    pr["baseRefOid"] = case["since"]
    assert merge(pr, [approved(1, "area:web")], CARRY)[0].startswith(
        "PR #7: the newest verifier review is on"
    )
    assert capsys.readouterr().out.splitlines() == [
        f"PR #7: {case['merge']} carries nothing from {case['head']}: its second parent {case['base']} is not on main"
    ]
